"""Public-reference ISO12233 chart reconstructions, not certified standard targets.

One scene describes SVG geometry and float reflectance sampling. Main patterns
are evaluated analytically; reference JPEG pixels never enter simulation data.
"""
from functools import lru_cache
import io
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

import drawsvg as draw
import numpy as np
from PIL import Image
import pymupdf

from iso12233.generate_chart import ROOT, draw_label
from iso12233.linear_output import linear_to_srgb


def load_profiles():
    return json.loads((ROOT / "data/modern_profiles.json").read_text())


def point(origin, angle, s, u=0):
    a = math.radians(angle)
    return [origin[0]+s*math.cos(a)-u*math.sin(a),
            origin[1]+s*math.sin(a)+u*math.cos(a)]


class Scene:
    def __init__(self, name, width, height, background, ink, profile):
        self.name, self.width, self.height = name, width, height
        self.background, self.ink, self.profile = background, ink, profile
        self.shapes, self.labels = [], []

    def add(self, kind, bounds, **params):
        self.shapes.append(dict(kind=kind, bounds=[float(v) for v in bounds], **params))

    def rect(self, x, y, w, h, value):
        self.add("rect", [x,y,x+w,y+h], value=value)

    def polygon(self, vertices, value):
        xy = np.asarray(vertices)
        self.add("polygon", [*xy.min(axis=0), *xy.max(axis=0)], vertices=vertices, value=value)

    def circle(self, x, y, radius, value):
        self.add("circle", [x-radius,y-radius,x+radius,y+radius], center=[x,y],
                 radius=radius, value=value)

    def label(self, x, y, text, size=2.8):
        self.labels.append(dict(x=x, y=y, text=str(text), size=size, fill="black"))

    def axial(self, kind, origin, angle, length, half_width, **params):
        corners = [point(origin, angle, s, u) for s in (0,length) for u in (-half_width,half_width)]
        xy = np.asarray(corners)
        self.add(kind, [*xy.min(axis=0),*xy.max(axis=0)], origin=origin, angle=angle,
                 length=length, **params)


def framing(scene, light, active_light, ratios):
    scene.rect(20,20,300,200,active_light)
    for x in (20,170,320):
        scene.polygon([[x,20],[x-3,10],[x+3,10]], light)
        scene.polygon([[x,220],[x-3,230],[x+3,230]], light)
    for y in (20,120,220):
        scene.polygon([[20,y],[10,y-3],[10,y+3]], light)
        scene.polygon([[320,y],[330,y-3],[330,y+3]], light)
    for ratio, text in ratios:
        delta = (300-200*ratio)/2
        for x in (20+delta,320-delta):
            scene.rect(x-0.6,20,1.2,10,scene.ink)
            scene.rect(x-0.6,210,1.2,10,scene.ink)
            for y in (20,220):
                scene.polygon([[x,y],[x-10,y],[x-10,y+(3 if y==20 else -3)]],scene.ink)
                scene.polygon([[x,y],[x+10,y],[x+10,y+(3 if y==20 else -3)]],scene.ink)
            scene.label(x+1.4,30,text,2.8)
            scene.label(x+1.4,217,text,2.8)


def slanted_star(scene, cx, cy, side, dark, angle):
    half = side/2
    def ray(a):
        dx, dy = math.sin(a), -math.cos(a)
        scale = half/max(abs(dx),abs(dy))
        return [cx+scale*dx,cy+scale*dy]
    start = math.radians(angle)
    for k in range(4):
        a, b = start+k*math.pi/2, start+k*math.pi/2+math.pi/4
        verts = [[cx,cy],ray(a)]
        for corner in [math.pi/4+i*math.pi/2 for i in range(5)]:
            if a < corner < b:
                verts.append(ray(corner))
        verts.append(ray(b))
        scene.polygon(verts,dark)
        scene.shapes[-1]["role"]="esfr_edge"
        scene.shapes[-1]["star_center"]=[cx,cy]


def build_esfr(profile):
    p = profile["parameters"]
    scene = Scene("esfr2024",340,240,p["border"],p["border"],profile)
    framing(scene,p["white"],p["background"],[(1.5,"3:2"),(4/3,"4:3")])
    for cx,cy in p["star_centers"]:
        slanted_star(scene,cx,cy,p["star_side_mm"],p["dark"],p["edge_start_deg"])
    # Public examples stagger the two middle patches outward on each face.
    patch=p["patch_size_mm"]
    levels=np.geomspace(*p["oecf_endpoints"],16)
    ordering={"top":[14,16,15,13],"bottom":[4,2,1,3],
              "left":[12,10,8,6],"right":[11,9,7,5]}
    for face,indices in ordering.items():
        for i,index in enumerate(indices):
            s=(i-2)*patch
            inner=i in (1,2)
            outward=(3.5 if inner else 3)*patch
            if face=="top": x,y=170+s,120-outward
            elif face=="bottom": x,y=170+s,120+outward-patch
            elif face=="left": x,y=170-outward,120+s
            else: x,y=170+outward-patch,120+s
            scene.rect(x,y,patch,patch,float(levels[index-1]))
            scene.shapes[-1].update(role="oecf",patch_index=index)
            # Text goes in the adjacent gap; it never supplies a reflectance value.
            tx,ty=x+patch/2-1.3,y+patch+2.7
            if face=="bottom": ty=y-1
            if face=="left": tx,ty=x+patch+0.7,y+patch/2+0.8
            if face=="right": tx,ty=x-3.4,y+patch/2+0.8
            scene.label(tx,ty,index,2.3)
    for cx,cy in p["registration_centers"]:
        scene.circle(cx,cy,p["registration_radius_mm"],scene.ink)
    r=p["focus_radius_mm"]
    scene.add("zoneplate",[170-r,120-r,170+r,120+r],center=[170,120],radius=r,
              cycles=12,low=p["dark"],high=p["white"])
    return scene


def build_ssfr(profile, layout, cycles):
    p=profile["parameters"]
    cw,ch=p["cell_size_mm"]
    gap=p["column_gap_mm"]
    rows,cols=(3,3) if layout=="grid" else (1,1)
    scene=Scene("ssfr",cols*cw+(cols-1)*gap,rows*ch,p["gap_background"],
                p["black"],profile)
    patch_xy=p["patch_positions_mm"]
    levels=np.linspace(p["white"],p["black"],16)
    for row in range(rows):
        for col in range(cols):
            ox,oy=col*(cw+gap),row*ch
            scene.rect(ox,oy,cw,ch,p["background"])
            cx,cy=ox+145,oy+135
            r=p["radius_mm"]
            scene.add("star",[cx-r,cy-r,cx+r,cy+r],center=[cx,cy],radius=r,
                      inner_radius=r*p["inner_radius_fraction"],cycles=cycles,
                      phase=p["phase_rad"],low=p["black"],high=p["white"],
                      background=p["background"])
            for x,y in ((0,0),(250,0),(0,240),(250,240)):
                scene.rect(ox+x,oy+y,40,30,p["black"])
            for x,y in p["marker_holes_mm"]:
                scene.rect(ox+x,oy+y,8,8,p["white"])
            for (x,y),level in zip(patch_xy,levels):
                scene.rect(ox+x,oy+y,20,20,float(level))
                scene.shapes[-1].update(role="linearization_patch",target_index=row*cols+col,
                                        patch_index=list(patch_xy).index([x,y])+1)
    return scene


def add_wedge(scene, origin, angle, length, f0, f1, height, low, high, labels=True):
    half=4.5*height/f0
    # Quiet zones stop reference circles from crossing the frequency targets.
    xy=np.asarray([point(origin,angle,s,u) for s in (-2,length+2) for u in (-half-2,half+2)])
    scene.polygon([xy[0].tolist(),xy[1].tolist(),xy[3].tolist(),xy[2].tolist()],high)
    scene.axial("wedge",origin,angle,length,half,f0=f0,f1=f1,
                active_height=height,value=low)
    if labels:
        for f in range(int(f0),int(f1)+1,100):
            s=length*(f-f0)/(f1-f0)
            q=height/f
            pos=point(origin,angle,s,4.5*q+1)
            end=point(origin,angle,s,4.5*q+2.6)
            dx,dy=end[0]-pos[0],end[1]-pos[1]
            n=math.hypot(dx,dy)
            perp=[-dy/n*0.075,dx/n*0.075]
            scene.polygon([[pos[0]+perp[0],pos[1]+perp[1]],
                           [end[0]+perp[0],end[1]+perp[1]],
                           [end[0]-perp[0],end[1]-perp[1]],
                           [pos[0]-perp[0],pos[1]-perp[1]]],low)
            if f in (200,500,1000,1500,2000,2500):
                x,y=point(origin,angle,s,4.5*q+4)
                scene.label(x-2,y+1,f//100,2.8)


def add_sweep(scene, origin, angle, length, f0, f1, low, high):
    corners=[point(origin,angle,s,u) for s,u in ((-1,-4.5),(length+1,-4.5),
                                               (length+1,4.5),(-1,4.5))]
    scene.polygon(corners,high)
    scene.axial("sweep",origin,angle,length,3.5,width=7,f0=f0,f1=f1,
                active_height=200,value=low)
    side=-1 if f0>=1400 else 1
    if f0>=1400:
        scene.polygon([point(origin,angle,s,u) for s,u in
                       ((-9,-3.5),(-2,-3.5),(-2,3.5),(-9,3.5))],low)
    for f in range(int(f0),int(f1)+1,100):
        s=length*(f-f0)/(f1-f0)
        pos=point(origin,angle,s,side*5)
        scene.circle(*pos,0.15,low)
        if f in (200,500,1000,1500,2000,2500):
            x,y=point(origin,angle,s,side*7)
            scene.label(x-2,y+1,f//100,2.8)


def build_cipa(profile):
    p=profile["parameters"]
    scene=Scene("cipa",340,240,p["black"],p["black"],profile)
    low,high=p["black"],p["white"]
    framing(scene,high,high,[(1.5,"3:2"),(4/3,"4:3"),(1,"1:1")])
    for r in p["reference_circle_radii_mm"]:
        scene.add("ring",[170-r-0.06,120-r-0.06,170+r+0.06,120+r+0.06],center=[170,120],
                  radius=r,width=0.12,value=low,clip=[20,20,320,220])
    for x,y,angle in p["peripheral_wedges"]:
        add_wedge(scene,[x,y],angle,p["peripheral_length_mm"],200,900,200,low,high,False)
    for cx,cy,angle in p["squares"]:
        scene.polygon([point([cx,cy],angle,s,u) for s,u in
                       ((-6.5,-6.5),(6.5,-6.5),(6.5,6.5),(-6.5,6.5))],low)
    for x,y,angle in p["main_wedges"]:
        add_wedge(scene,[x,y],angle,p["main_length_mm"],200,2500,200,low,high)
    for origin,angle,length,f0,f1 in p["sweeps"]:
        add_sweep(scene,origin,angle,length,f0,f1,low,high)
    scene.circle(170,120,9,high)
    scene.add("wheel",[162.5,112.5,177.5,127.5],center=[170,120],radius=7.5,
              cycles=6,value=low)
    scene.rect(119,0,102,5,high)
    scene.label(127,4,"Values in 100X Lines per Picture Height",3.1)
    return scene


def build_scene(name, layout="grid", cycles=144):
    profile=load_profiles()[name]
    if name=="esfr2024": return build_esfr(profile)
    if name=="cipa": return build_cipa(profile)
    return build_ssfr(profile,layout,cycles)


def sample_scene(scene, xs, ys):
    """Evaluate continuous reflectance at global sample coordinates (float64)."""
    result=np.full((len(ys),len(xs)),scene.background,dtype=np.float32)
    for shape in scene.shapes:
        x0,y0,x1,y1=shape["bounds"]
        if "clip" in shape:
            a,b,c,d=shape["clip"]
            x0,y0,x1,y1=max(x0,a),max(y0,b),min(x1,c),min(y1,d)
        ix0,ix1=np.searchsorted(xs,[x0,x1],side="left")
        iy0,iy1=np.searchsorted(ys,[y0,y1],side="left")
        if ix0==ix1 or iy0==iy1: continue
        x,y=xs[None,ix0:ix1],ys[iy0:iy1,None]
        target=result[iy0:iy1,ix0:ix1]
        kind=shape["kind"]
        mask=None
        if kind=="rect": target[:]=shape["value"]; continue
        if kind=="polygon":
            vertices=shape["vertices"]
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(vertices,vertices[1:]+vertices[:1]))
            mask=np.ones(target.shape,dtype=bool)
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):
                cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
                mask &= cross*np.sign(area)>=0
        elif kind in ("wedge","sweep"):
            a=math.radians(shape["angle"])
            dx,dy=x-shape["origin"][0],y-shape["origin"][1]
            s=dx*math.cos(a)+dy*math.sin(a)
            u=-dx*math.sin(a)+dy*math.cos(a)
            inside=(s>=0)&(s<shape["length"])
            if kind=="wedge":
                f=shape["f0"]+(shape["f1"]-shape["f0"])*s/shape["length"]
                normalized=u*f/shape["active_height"]
                mask=inside&(np.abs(normalized)<4.5)&(np.floor(normalized+4.5)%2==0)
            else:
                phase=s*(shape["f0"]+(shape["f1"]-shape["f0"])*s/(2*shape["length"]))/(
                    2*shape["active_height"])
                mask=inside&(np.abs(u)<shape["width"]/2)&(np.floor(2*phase)%2==0)
        else:
            dx,dy=x-shape["center"][0],y-shape["center"][1]
            radius=np.hypot(dx,dy)
            inside=radius<shape["radius"]
            if kind=="star":
                theta=np.arctan2(dy,dx)
                value=(shape["high"]+shape["low"])/2+(shape["high"]-shape["low"])/2*np.cos(
                    shape["cycles"]*theta+shape["phase"])
                inner=radius<shape["inner_radius"]
                value=np.where(inner,np.where(dx*dy>=0,shape["low"],shape["high"]),value)
                target[inside]=value[inside]
                continue
            if kind=="circle": mask=inside
            elif kind=="ring": mask=np.abs(radius-shape["radius"])<shape["width"]/2
            elif kind=="wheel": mask=inside&(np.floor(np.arctan2(dy,dx)*shape["cycles"]/math.pi)%2==0)
            elif kind=="zoneplate":
                phase=shape["cycles"]*(radius/shape["radius"])**2
                phase=np.where(dx<0,phase*0.65,phase)
                value=np.where(np.floor(2*phase)%2==0,shape["low"],shape["high"])
                target[inside]=value[inside]
                continue
            else: raise ValueError(kind)
        target[mask]=shape["value"]
    return result


def label_coverage(scene,width,height):
    if not scene.labels: return None
    d=draw.Drawing(scene.width,scene.height)
    d.append(draw.Rectangle(0,0,scene.width,scene.height,fill="white"))
    for label in scene.labels: d.append(draw_label(label))
    with pymupdf.open(stream=d.as_svg().encode(),filetype="svg") as doc:
        page=doc[0]
        pix=page.get_pixmap(matrix=pymupdf.Matrix(width/page.rect.width,height/page.rect.height),
                           colorspace=pymupdf.csGRAY,alpha=False)
        return np.frombuffer(pix.samples,dtype=np.uint8).reshape(height,width).copy()


def raster_blocks(scene,width,supersample=4,tile_rows=16):
    if width<32 or supersample<1 or tile_rows<1: raise ValueError("Invalid sampling dimensions")
    height=round(width*scene.height/scene.width)
    xs=(np.arange(width*supersample,dtype=np.float64)+0.5)*scene.width/(width*supersample)
    labels=label_coverage(scene,width,height)
    for y0 in range(0,height,tile_rows):
        y1=min(height,y0+tile_rows)
        ys=(np.arange(y0*supersample,y1*supersample,dtype=np.float64)+0.5)*scene.height/(height*supersample)
        samples=sample_scene(scene,xs,ys)
        block=samples.reshape(y1-y0,supersample,width,supersample).mean(axis=(1,3),dtype=np.float32)
        if labels is not None:
            alpha=labels[y0:y1].astype(np.float32)/255
            block=block*alpha+scene.ink*(1-alpha)
        yield y0,block


def render_linear(scene,destination,width,supersample=4,tile_rows=16):
    height=round(width*scene.height/scene.width)
    destination.parent.mkdir(parents=True,exist_ok=True)
    output=np.lib.format.open_memmap(destination,mode="w+",dtype=np.float32,shape=(height,width))
    low,high,total=1.0,0.0,0.0
    for y0,block in raster_blocks(scene,width,supersample,tile_rows):
        output[y0:y0+len(block)]=block
        low,high=min(low,float(block.min())),max(high,float(block.max()))
        total+=float(block.sum(dtype=np.float64))
    output.flush()
    del output
    return dict(width=width,height=height,dtype="float32",minimum=low,maximum=high,
                mean=total/(width*height),supersample=supersample,tile_rows=tile_rows,
                sampling="uniform box integration of analytic reflectance samples",
                gamma_applied=False,label_coverage="MuPDF native-resolution 8-bit coverage")


def color(value):
    level=int(round(float(linear_to_srgb(value))*255))
    return f"#{level:02x}{level:02x}{level:02x}"


@lru_cache(maxsize=8)
def star_bitmap(pixels,radius,inner_radius,cycles,phase,low,high,background,supersample):
    scene=Scene("asset",2*radius,2*radius,background,low,{})
    scene.add("star",[0,0,2*radius,2*radius],center=[radius,radius],radius=radius,
              inner_radius=inner_radius,cycles=cycles,phase=phase,low=low,high=high,background=background)
    image=Image.new("L",(pixels,pixels))
    for y0,block in raster_blocks(scene,pixels,supersample):
        encoded=np.rint(np.clip(linear_to_srgb(block),0,1)*255).astype(np.uint8)
        image.paste(Image.fromarray(encoded),(0,y0))
    buffer=io.BytesIO()
    image.save(buffer,format="PNG")
    return buffer.getvalue()


def build_svg(scene,width=8192,supersample=4):
    d=draw.Drawing(scene.width,scene.height)
    d.set_render_size(f"{scene.width}mm",f"{scene.height}mm")
    d.append_title(f"{scene.name}: public-reference ISO12233 reconstruction")
    d.append(draw.Raw("<desc>Approximate public-reference reconstruction. Not certified ISO-compliant. "
                          "See data/modern_profiles.json for measured and selected parameters.</desc>"))
    d.append(draw.Raw("<metadata>"+escape(json.dumps(scene.profile,sort_keys=True))+"</metadata>"))
    d.append(draw.Rectangle(0,0,scene.width,scene.height,fill=color(scene.background)))
    images={}
    for shape in scene.shapes:
        kind=shape["kind"]
        style={"fill":color(shape.get("value",0))}
        elem=None
        if kind=="rect":
            x0,y0,x1,y1=shape["bounds"]
            elem=draw.Rectangle(x0,y0,x1-x0,y1-y0,**style)
        elif kind=="polygon": elem=draw.Lines(*np.asarray(shape["vertices"]).ravel(),close=True,**style)
        elif kind in ("circle","ring"):
            if kind=="ring": style=dict(fill="none",stroke=style["fill"],stroke_width=shape["width"])
            elem=draw.Circle(*shape["center"],shape["radius"],**style)
        elif kind in ("wedge","sweep"):
            group=draw.Group()
            if kind=="wedge":
                frequencies=np.geomspace(shape["f0"],shape["f1"],512)
                ss=shape["length"]*(frequencies-shape["f0"])/(shape["f1"]-shape["f0"])
                for k in (-4,-2,0,2,4):
                    points=[point(shape["origin"],shape["angle"],float(s),float((k-0.5)*shape["active_height"]/f)) for s,f in zip(ss,frequencies)]
                    points += [point(shape["origin"],shape["angle"],float(s),float((k+0.5)*shape["active_height"]/f)) for s,f in zip(ss[::-1],frequencies[::-1])]
                    group.append(draw.Lines(*np.asarray(points).ravel(),close=True,**style))
            else:
                a=shape["f0"]/(2*shape["active_height"])
                b=(shape["f1"]-shape["f0"])/(4*shape["active_height"]*shape["length"])
                maxphase=a*shape["length"]+b*shape["length"]**2
                def root(p): return 2*p/(a+math.sqrt(a*a+4*b*p))
                for k in range(0,math.ceil(2*maxphase),2):
                    start,end=root(k/2),min(shape["length"],root((k+1)/2))
                    vertices=[point(shape["origin"],shape["angle"],s,u) for s,u in
                              ((start,-3.5),(end,-3.5),(end,3.5),(start,3.5))]
                    group.append(draw.Lines(*np.asarray(vertices).ravel(),close=True,**style))
            elem=group
        elif kind=="star":
            pixels=max(32,round(2*shape["radius"]*width/scene.width))
            key=tuple(shape[k] for k in ("radius","inner_radius","cycles","phase","low","high","background"))
            if key not in images:
                bitmap=star_bitmap(pixels,*key,supersample)
                img=draw.Image(0,0,2*shape["radius"],2*shape["radius"],data=bitmap,
                               mime_type="image/png",id=f"analytic-star-{len(images)}")
                d.append_def(img)
                images[key]=img
            elem=draw.Use(images[key],shape["center"][0]-shape["radius"],
                          shape["center"][1]-shape["radius"],data_raster_width=pixels)
        elif kind=="wheel":
            group=draw.Group()
            for k in range(shape["cycles"]):
                a=k*2*math.pi/shape["cycles"]
                b=a+math.pi/shape["cycles"]
                cx,cy=shape["center"]; r=shape["radius"]
                group.append(draw.Path(**style).M(cx,cy).L(cx+r*math.cos(a),cy+r*math.sin(a)).A(
                    r,r,0,0,1,cx+r*math.cos(b),cy+r*math.sin(b)).Z())
            elem=group
        elif kind=="zoneplate":
            # SVG-only miniature bitmap; linear output still evaluates the formula.
            pixels=max(32,round(2*shape["radius"]*width/scene.width))
            r=shape["radius"]
            mini=Scene("focus",2*r,2*r,shape["high"],shape["low"],{})
            mini.add("zoneplate",[0,0,2*r,2*r],center=[r,r],radius=r,
                     cycles=shape["cycles"],low=shape["low"],high=shape["high"])
            image=Image.new("L",(pixels,pixels))
            for y0,block in raster_blocks(mini,pixels,supersample):
                image.paste(Image.fromarray(np.rint(linear_to_srgb(block)*255).astype(np.uint8)),(0,y0))
            buf=io.BytesIO(); image.save(buf,format="PNG")
            # Clip to circle so the raster's background does not replace star edges.
            clip=draw.ClipPath(); clip.append(draw.Circle(*shape["center"],r))
            elem=draw.Image(shape["center"][0]-r,shape["center"][1]-r,2*r,2*r,
                            data=buf.getvalue(),mime_type="image/png",clip_path=clip)
        if "clip" in shape:
            x0,y0,x1,y1=shape["clip"]
            clip=draw.ClipPath(); clip.append(draw.Rectangle(x0,y0,x1-x0,y1-y0))
            elem=draw.Group([elem],clip_path=clip)
        d.append(elem)
    for label in scene.labels:
        item=dict(label,fill=color(scene.ink))
        d.append(draw_label(item))
    return d.as_svg()
