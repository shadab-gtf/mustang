from math import cos, pi, sin

import bpy

from body import count, grid, shoulder
from geometry import box, lathe, panel, parent_world, plate, sample, tube


def front_y(x):
    return 2.285-.073*(abs(x)/.90)**3


def rear_y(x):
    return -2.282+.149*(abs(x)/.91)**3


def contour(positions, surface, offset=0):
    return [(x,surface(x)+offset,z) for x,z in positions]


def text_mesh(name, value, location, size, material, parent, *, rear=False, tracking=1):
    curve = bpy.data.curves.new(name,"FONT")
    curve.body = value
    curve.align_x = "CENTER"
    curve.size = size
    curve.space_character = tracking
    curve.extrude = .00065
    curve.materials.append(material)
    obj = bpy.data.objects.new(name,curve)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (pi/2,0,0 if rear else pi)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.view_layer.objects.active
    obj.select_set(False)
    if not obj.data.uv_layers:
        layer = obj.data.uv_layers.new(name="UVMap")
        for loop in obj.data.loops:
            pos = obj.data.vertices[loop.vertex_index].co
            layer.data[loop.index].uv = (pos.x, pos.y)
    return parent_world(obj,parent)


def bumper(ctx, name, surface, front):
    m, p = ctx.materials, ctx.root
    direction = 1 if front else -1
    line = grid(-.882,.882,count(ctx.detail,44,15))
    rows = []
    for x in line:
        t = abs(x)/.882
        z = .506+.025*t*t if front else .476+.036*t*t
        nose = surface(x)+direction*(.058+.036*t*t)
        rows.append([(x,nose-direction*d,z+height) for d,height in
                     [(.035,-.029),(.013,-.023),(.002,-.008),(0,.005),(.008,.020),(.027,.029),(.040,.030)]])
    panel(name,rows,m["chrome"],p,thickness=(0,-direction*.039,0))
    tube(name+" lower gasket",[(row[0][0],row[0][1],row[0][2]-.004) for row in rows],
         .007,m["dark"],p,sides=8)


def front(ctx):
    p, m = ctx.root, ctx.materials
    outer = [(-.874,.545),(-.884,.63),(-.838,.744),(-.745,.773),(-.648,.773),
             (-.556,.792),(.556,.792),(.648,.773),(.745,.773),(.838,.744),(.884,.63),
             (.874,.545)]
    plate("Front fascia backing",contour(outer,front_y,-.027),m["paint"],p,radius=.017)
    mouth = [(-.576,.570),(-.627,.724),(-.596,.769),(.596,.769),(.627,.724),(.576,.570)]
    plate("Hexagonal grille recess",contour(mouth,front_y,.001),m["black"],p,radius=.014)
    tube("Grille stainless surround",contour(mouth,front_y,.009),.009,m["chrome"],p,
         closed=True,sides=10)
    if ctx.detail < 3:
        for x in grid(-.572,.572,count(ctx.detail,68,22)):
            bottom=.581 + .035*max(0,min(1,(abs(x)-.55)/.03))
            tube("Stamped grille vertical web",[(x,front_y(x)+.009,bottom),(x,front_y(x)+.009,.758)],
                 .0016,m["dark"],p,sides=5)
        for z in grid(.583,.757,count(ctx.detail,13,6)):
            w=.57+.034*sin(min((z-.58)/.18,1)*pi)
            tube("Stamped grille horizontal web",[(x,front_y(x)+.012,z) for x in grid(-w,w,12)],
                 .0016,m["dark"],p,sides=5)
    bumper(ctx,"Front chrome bumper",front_y,True)

    valance = [(-.868,.516),(-.856,.452),(-.757,.359),(-.335,.347),(-.273,.367),
               (.273,.367),(.335,.347),(.757,.359),(.856,.452),(.868,.516)]
    plate("Front lower valance",contour(valance,front_y,.013),m["paint"],p,radius=.019)
    corner=[(.359,.757),(.454,.854),(.549,.875),(.637,.884),(.732,.836),(.754,.754)]
    for side in (-1,1):
        rows=[]
        for z in grid(.359,.754,count(ctx.detail,22,9)):
            tip=side*sample(corner,z)[0]
            body=shoulder(2.255,side,z)
            y_edge=front_y(tip)+.010
            rows.append([(body+(tip-body)*t,2.255+(y_edge-2.255)*t-.021*sin(pi*t),z)
                         for t in grid(0,1,6)])
        panel("Headlight fascia return",rows,m["paint"],p,thickness=(0,-.008,0))
    intake = [(-.405,.471),(-.34,.372),(.34,.372),(.405,.471)]
    plate("Lower duct aperture",contour(intake,front_y,.023),m["black"],p,radius=.012)
    tube("Lower duct rolled border",contour(intake,front_y,.028),.008,m["dark"],p,closed=True)
    box("Intercooler bar and plate core",(0,2.304,.419),(.623,.028,.089),m["alloy"],p,radius=.007)
    for z in grid(.388,.450,count(ctx.detail,15,5)):
        box("Intercooler fin shadow",(0,2.320,z),(.599,.003,.0018),m["dark"],p,radius=0)
    for x in (-.330,.330):
        box("Intercooler end tank",(x,2.279,.417),(.054,.078,.097),m["alloy"],p,radius=.019)
    tube("Lower splitter edge",contour([(-.727,.349),(-.541,.335),(-.334,.336),
         (0,.342),(.334,.336),(.541,.335),(.727,.349)], front_y,.030),.014,m["dark"],p,sides=9)

    for side, key in ((-1,"L"),(1,"R")):
        x=.733*side
        y=front_y(x)
        z=.653
        sega=count(ctx.detail,72,22)
        flare = [(x+(1 if side<0 else -1)*.121,.569),
                 (x+side*.131,.559),(x+side*.137,.666),(x+side*.085,.738),
                 (x-side*.057,.756),(x-side*.118,.724)]
        plate("Headlamp bucket shell "+key,contour(flare,front_y,-.008),m["paint"],p,radius=.012)
        lathe("Headlamp recess "+key,(x,y+.012,z),
              [(-.028,.102),(.027,.102),(.025,.076),(-.018,.076)],1,m["black"],p,segments=sega)
        lathe("Chrome headlamp bezel "+key,(x,y+.022,z),
              [(-.007,.089),(.006,.093),(.017,.090),(.024,.084),(.023,.074),(.016,.074),(.001,.078)],
              1,m["chrome"],p,segments=sega)
        lathe("Sealed beam reflector "+key,(x,y+.034,z),
              [(-.028,.013),(-.013,.060),(.001,.075),(.005,.075),(-.009,.060),(-.022,.011)],
              1,m["alloy"],p,segments=sega)
        lathe("Low beam filament capsule "+key,(x-.024,y+.035,z-.006),
              [(-.008,.004),(0,.026),(.014,.025),(.017,.003)],1,m["low"],p,segments=24)
        lathe("High beam filament capsule "+key,(x+.025,y+.037,z+.009),
              [(-.010,.004),(0,.022),(.012,.022),(.015,.003)],1,m["high"],p,segments=24)
        lathe("Optical lens "+key,(x,y+.051,z),
              [(-.003,.073),(.002,.074),(.010,.059),(.017,.024),(.018,.0002),
               (.011,.0002),(.010,.024),(.003,.059)],1,m["lens"],p,segments=sega)
        if ctx.detail < 2:
            for groove in grid(-.055,.055,11):
                lens_height=.88*(.069**2-groove**2)**.5
                tube("Headlight optical flute "+key,
                     [(x+groove,y+.052+d*.009,z+(2*d-1)*lens_height) for d in grid(0,1,4)],
                     .0007,m["lens"],p,sides=5)
        box("Front turn lamp recess "+key,(side*.662,front_y(.662)+.019,.439),(.138,.022,.065),
            m["dark"],p,radius=.022)
        box("Front amber turn lamp "+key,(side*.662,front_y(.662)+.032,.439),(.103,.013,.036),
            m["Front"+key],p,radius=.011)


def rear(ctx):
    p,m=ctx.root,ctx.materials
    rear_panel=[(-.859,.510),(-.849,.733),(-.768,.798),(-.629,.809),(.629,.809),
                (.768,.798),(.849,.733),(.859,.510)]
    plate("Tail outer pressing",contour(rear_panel,rear_y,-.004),m["paint"],p,depth=(0,.030,0),radius=.014)
    inset = [(-.734,.556),(-.766,.740),(-.688,.773),(.688,.773),(.766,.740),(.734,.556)]
    plate("Recessed rear panel",contour(inset,rear_y,-.021),m["dark"],p,depth=(0,.012,0),radius=.014)
    tube("Recessed rear panel border",contour(inset,rear_y,-.024),.004,m["chrome"],p,closed=True,sides=8)
    bumper(ctx,"Rear chrome bumper",rear_y,False)
    plate("Rear lower apron",contour([(-.81,.465),(-.745,.377),(-.418,.356),(.410,.356),
          (.746,.377),(.81,.465)],rear_y,-.004),m["paint"],p,depth=(0,.022,0),radius=.015)
    for side,key in ((-1,"L"),(1,"R")):
        for bar in range(3):
            x=side*(.447+.091*bar)
            z=.666+.005*bar
            box("Tri-bar bright bezel "+key,(x,rear_y(x)-.029,z),(.074,.038,.169),m["chrome"],p,radius=.012)
            box("Tri-bar red lens "+key,(x,rear_y(x)-.050,z),(.053,.011,.145),m["red"],p,radius=.008)
            for index in range(2):
                emission=["tail","brake","Rear"+key][bar]
                box("Inset tri-bar lens optic "+key,(x+(index-.5)*.018,rear_y(x)-.057,z),
                    (.014,.004,.129),m[emission],p,radius=.004)
        x=side*.676
        lathe("Reverse lamp bezel "+key,(x,rear_y(x)-.009,.412),
              [(-.009,.036),(.014,.035),(.017,.027),(-.010,.026)],1,m["chrome"],p,segments=26)
        lathe("Reverse lamp optic "+key,(x,rear_y(x)-.020,.412),
              [(-.012,.001),(-.009,.029),(.003,.031),(.005,.0003)],1,m["reverse"],p,segments=26)
    lathe("Machined fuel cap surround",(0,-2.313,.657),
          [(-.007,.069),(.011,.067),(.016,.058),(.021,.049),(-.008,.047)],
          1,m["chrome"],p,segments=count(ctx.detail,64,20))
    lathe("Fuel cap center",(0,-2.321,.657),
          [(-.004,.0003),(-.003,.049),(.007,.052),(.009,.0003)],1,m["dark"],p,segments=48)
    if ctx.detail <= 2:
        text_mesh("Rear panel lettering","M U S T A N G",(0,-2.306,.751),.020,m["chrome"],p,rear=True)
        box("Rear registration base",(0,-2.306,.439),(.245,.016,.072),m["dark"],p,radius=.008)
        text_mesh("Rear registration lettering","67 · 108",(0,-2.316,.422),.030,m["stripe"],p,rear=True)
        text_mesh("Fuel cap lettering","GT",(0,-2.325,.641),.038,m["chrome"],p,rear=True)


def build_fascia(ctx):
    front(ctx)
    rear(ctx)
