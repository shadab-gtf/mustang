from dataclasses import replace
from math import cos, sin, tau

import bpy

from exhaust import ORIGIN
from geometry import pivot
from materials import pbr
from mechanicals import (
    MeshBatch, build_cabin_hardware, build_dash, build_seats, build_steering,
    build_trunk, finishes, lettering, pipe, rounded, sweep,
)
from source_panels import extract_mesh, material_islands


def engine_bay(chassis, m):
    engine = pivot("Engine", (0, 1.28, .46), chassis)
    bay = MeshBatch("V8 engine bay, radiator and triangulated bracing", chassis)
    motor = MeshBatch("V8 block, induction, valve covers and accessories", engine)
    aluminum = m.steel
    enamel = pbr("Satin black engine enamel", (.024, .026, .027), .30, .32, coat=.31)
    filter_paper = pbr("Rose cotton air-filter pleats", (.24, .087, .079), .72)
    battery_red = pbr("Red battery casing", (.39, .027, .021), .34)
    belt = pbr("Serpentine belt", (.017, .018, .020), .68)

    rounded(motor, m.cast, (0, 1.29, .401), (.443, .626, .302), .052)
    rounded(motor, aluminum, (0, 1.312, .528), (.345, .435, .144), .037)
    rounded(motor, aluminum, (0, 1.286, .630), (.246, .275, .10), .033)
    rounded(motor, m.cast, (0, 1.28, .682), (.196, .164, .059), .014)
    for sign in (-1, 1):
        x = sign * .235
        rounded(motor, m.cast, (x*.9, 1.27, .536), (.20, .63, .152), .034)
        rounded(motor, enamel, (x, 1.272, .650), (.166, .583, .106), .037)
        for offset in (-.044, -.023, .023, .044):
            rounded(motor, aluminum, (x+offset, 1.273, .702), (.008, .451, .004), .0018, segments=2)
        sweep(motor, aluminum, ((x, 1.110, .694), (x, 1.110, .720)), .023, segments=20)
        for y in (1.055, 1.18, 1.33, 1.475):
            for side in (-1, 1):
                sweep(motor, aluminum, ((x+side*.07,y,.669),(x+side*.07,y,.678)), .007, segments=8)
            pipe(motor, m.heat, (
                (sign*.315,y,.555), (sign*.382,y-.025,.510), (sign*.386,y-.06,.395),
                (sign*.309,1.035,.300), (sign*.266,.85,.242),
            ), .0175, segments=9)
            pipe(motor, m.hose, ((0,1.558,.587),(sign*.13,1.54,.610),
                (sign*.265,y+.038,.646),(sign*.313,y,.582)), .0043, segments=6)

    # Oval top with a recessed pleated filter, bright backing and twin brushed bands.
    center = (0, 1.288)
    shell = [(center[0]+.190*cos(tau*i/64), center[1]+.216*sin(tau*i/64), .788) for i in range(64)]
    motor.panel(enamel, shell, (0,0,.014))
    motor.panel(aluminum, [(x*.985,y,.722) for x,y,_ in shell], (0,0,.007))
    for i, (x,y,_) in enumerate(shell):
        x *= 1 if i%2 else .937
        y = center[1]+(y-center[1])*(1 if i%2 else .94)
        next_x,next_y,_ = shell[(i+1)%len(shell)]
        next_x *= 1 if i%2==0 else .937
        next_y = center[1]+(next_y-center[1])*(1 if i%2==0 else .94)
        motor.panel(filter_paper, [(x,y,.729),(next_x,next_y,.729),(next_x,next_y,.790),(x,y,.790)],
                    (-x*.007,-(y-center[1])*.007,0))
    for x in (-.047,.047):
        rounded(motor, aluminum, (x,1.295,.803), (.068,.370,.004), .0019, segments=2)
    for x,z,radius in ((0,.435,.077),(-.154,.503,.060),(.164,.485,.070),(.008,.566,.042)):
        sweep(motor, aluminum, ((x,1.605,z),(x,1.698,z)), radius*.79, segments=22)
        sweep(motor, belt, ((x,1.696,z),(x,1.723,z)), radius, segments=28)
        sweep(motor, aluminum, ((x,1.722,z),(x,1.735,z)), radius*.39, segments=18)
    sweep(motor, belt, [(-.20,1.709,.533),(-.06,1.709,.365),(.065,1.709,.368),
        (.227,1.709,.454),(.179,1.709,.551),(.010,1.709,.605),(-.122,1.709,.559)], .009, segments=8, closed=True)

    rounded(bay, aluminum, (0,1.966,.568), (1.037,.105,.315), .025)
    rounded(bay, enamel, (0,1.906,.554), (.864,.030,.241), .011)
    for x in (-.34,-.22,-.11,0,.11,.22,.34):
        rounded(bay, m.cast, (x,1.890,.558), (.009,.011,.212), .002)
    sweep(bay, aluminum, ((-.289,1.961,.725),(-.289,1.961,.752)), .036, segments=24)
    pipe(bay, m.hose, [(-.346,1.911,.700),(-.298,1.851,.748),(-.119,1.757,.742),(-.024,1.703,.672)], .031, segments=15)
    pipe(bay, m.hose, [(.347,1.923,.451),(.258,1.818,.429),(.121,1.706,.481)], .024, segments=12)
    rounded(bay, battery_red, (.464,1.71,.566), (.196,.244,.163), .013)
    rounded(bay, enamel, (.464,1.71,.650), (.197,.245,.031), .012)
    for x,mat in ((.406,m.cast),(.532,battery_red)):
        sweep(bay, mat, ((x,1.776,.666),(x,1.776,.685)), .018, segments=16)
    pipe(bay, m.hose, [(.406,1.776,.678),(.384,1.737,.659),(.402,1.655,.628),(.380,1.316,.548)], .009, segments=8)
    for sign in (-1, 1):
        x=sign*.514
        rounded(bay, enamel, (x,1.344,.585), (.250,.316,.267), .072)
        rounded(bay, aluminum, (x,1.342,.711), (.203,.203,.024), .021)
        sweep(bay, m.cast, ((x,1.34,.723),(x,1.34,.746)), .041, segments=26)
        for y in (1.270,1.417):
            sweep(bay, aluminum, ((x+sign*.062,y,.718),(x+sign*.062,y,.730)), .009, segments=8)
        pipe(bay, aluminum, [(x,1.387,.739),(sign*.377,1.578,.729),(sign*.224,1.618,.721)], .016, segments=12)
        pipe(bay, aluminum, [(x,1.310,.742),(sign*.388,1.044,.746),(sign*.303,.944,.727)], .017, segments=12)
    pipe(bay, aluminum, [(-.665,1.596,.722),(-.387,1.616,.741),(0,1.641,.747),(.39,1.62,.738),(.656,1.594,.718)], .019, segments=14)
    rounded(bay, enamel, (-.465,1.007,.666), (.120,.183,.112), .023)
    motor.finish()
    bay.finish()
    lettering("Raised air-cleaner lettering", engine, aluminum, (0,1.141,.807), "ROUSH", .034, (0,0,3.14159))


def underbody(chassis, m):
    source_meshes = [obj for obj in chassis.children if obj.type == "MESH"]
    for mat, names, count in (
        ("Satin black trim and chassis", {"Object_20","Object_38","Object_40"}, 604),
        ("Polished nickel brightwork", {"Object_72","Object_78","Object_82"}, 96),
    ):
        for island in material_islands(source_meshes,mat):
            if island.count != count or {obj.name for obj in island.faces} != names:
                continue
            for obj,indices in island.faces.items():
                hidden = set(indices) if count == 96 else {
                    index for index in indices if (
                        abs(obj.data.polygons[index].center.x) < .75 and
                        -2.2 < obj.data.polygons[index].center.y < 1.95 and
                        obj.data.polygons[index].center.z < .37 and
                        abs(obj.data.polygons[index].normal.z) > .48
                    )
                }
                if hidden:
                    remove_faces(obj,hidden)
            break
    parts = MeshBatch("Fuel tank, rear axle, leaf packs and dual exhaust routing", chassis)
    parts.panel(m.cast,[(-.636,-1.46,.407),(.636,-1.46,.407),(.672,.681,.378),(.53,1.38,.437),
        (-.53,1.38,.437),(-.672,.681,.378)],(0,0,-.026))
    parts.panel(m.cast,[(-.644,-2.166,.521),(.644,-2.166,.521),(.640,-1.465,.469),(-.640,-1.465,.469)],(0,0,-.026))
    for sign in (-1,1):
        rounded(parts,m.cast,(sign*.588,-.16,.375),(.092,2.366,.108),.020)
        rounded(parts,m.cast,(sign*.560,-1.79,.385),(.074,.710,.091),.013)
        for x in (.14,.219,.408,.477):
            rounded(parts,m.cast,(sign*x,-.127,.393),(.026,1.81,.023),.008)
    for y,z,w in ((-.43,.373,1.155),(.651,.365,1.193),(1.342,.346,1.182)):
        rounded(parts,m.cast,(0,y,z),(w,.108,.084),.018)
    rounded(parts, m.cast, (0,-1.869,.407), (1.058,.588,.199), .059)
    for x in (-.337,.337):
        rounded(parts, m.steel, (x,-1.869,.319), (.035,.56,.019), .006)
    for x in (-.425,-.21,0,.21,.425):
        rounded(parts, m.cast, (x,-1.856,.31), (.020,.391,.018), .007)
    sweep(parts, m.cast, ((-.709,-1.292,.297),(.709,-1.292,.297)), .036, segments=16)
    sweep(parts, m.cast, ((0,-1.14,.297),(0,-1.214,.298),(0,-1.292,.298),(0,-1.385,.297)),
          (.049,.086,.137,.098), segments=24)
    rounded(parts,m.cast,(0,.338,.331),(.279,.484,.205),.073)
    sweep(parts, m.steel, ((0,.102,.308),(0,-1.155,.296)), .036, segments=18)
    for side in (-1,1):
        for leaf in range(4):
            length = .64-leaf*.086
            stations=[]
            for i in range(13):
                t=i/6-1
                x=side*.535
                y=-1.292+length*t
                z=.255+.085*t*t-.009*leaf
                stations.append([(x-.031,y,z-.004),(x+.031,y,z-.004),(x+.031,y,z+.004),(x-.031,y,z+.004)])
            parts.loft(m.cast, stations, smooth=False)
        pipe(parts, m.steel, [(side*.586,-1.292,.261),(side*.540,-1.37,.368),(side*.505,-1.526,.495)], .018, segments=12)
        rounded(parts, m.cast, (side*.535,-1.29,.229), (.136,.106,.021), .007)
        for dx in (-.042,.042):
            for dy in (-.041,.041):
                sweep(parts, m.steel, ((side*.535+dx,-1.29+dy,.215),(side*.535+dx,-1.29+dy,.307)), .006, segments=8)
        x=side*.315
        pipe(parts, m.steel, [(side*.265,.86,.241),(x,.55,.205),(x,-.16,.188),(x,-.42,.189)], .027, segments=12)
        rounded(parts, m.heat, (x,-.65,.190), (.162,.457,.115), .050)
        pipe(parts, m.steel, [(x,-.873,.188),(x,-1.015,.206),(side*.364,-1.17,.352),
            (side*.421,-1.313,.418),(side*.427,-1.448,.383),(side*.388,-1.534,.319),
            (-.327,-1.630,.277)], .026, segments=12)
        sweep(parts,m.steel,((x,.515,.205),(x,.545,.205)),.049,segments=14)
        pipe(parts,m.cast,[(x,-.859,.221),(x+side*.050,-.861,.285),(x+side*.050,-.881,.326)],.009,segments=8)
    pipe(parts, m.steel, [(-.327,-1.620,.278),(-.394,-1.684,.256),tuple(ORIGIN)], .033, segments=16)
    parts.finish()


def remove_faces(obj, indices):
    source = obj.data
    remaining = [face.index for face in source.polygons if face.index not in indices]
    if remaining:
        obj.data = extract_mesh(source, remaining, source.name + " cleaned")
    else:
        bpy.data.objects.remove(obj, do_unlink=True)


def clean_race_cabin(chassis):
    meshes = [obj for obj in chassis.children_recursive if obj.type == "MESH"]
    removed = {}
    for material in ("Satin black trim and chassis", "Polished nickel brightwork", "Clear lamp optics"):
        for island in material_islands(meshes, material):
            low, high = island.minimum, island.maximum
            names = {obj.name for obj in island.faces}
            net = island.count == 1356 and names == {"Object_26", "Object_32", "Object_54"}
            net_bar = island.count == 256 and names == {"Object_26"} and high[0] < -.52 and low[2] > 1.08
            seats_and_wheel = (
                (island.count == 2224 and names == {"Object_52"} and high[2] < .96 and low[1] > -.61)
                or (names == {"Object_52"} and island.count == 2496 and -.39 < low[0] < -.36)
                or (names == {"Object_54"} and island.count == 5632 and -.48 < low[0] < -.45)
            )
            race_braces = (
                (names == {"Object_94"} and island.count == 6912 and low[1] < -1.68 and high[2] > 1.18)
                or (names == {"Object_96"} and island.count == 4416 and low[2] > 1.11 and high[0] > .61)
                or (names == {"Object_26"} and island.count == 256 and low[2] < .24
                    and high[2] > 1.15 and -.045 < low[1] < -.015 and high[1] > .40)
                or (names == {"Object_52"} and island.count == 496 and low[1] < -.635 and high[2] > 1.15)
                or (names == {"Object_26"} and island.count == 256 and -.94 < low[1] < -.93
                    and -.54 < high[1] < -.53 and high[2] > 1.15)
            )
            old_door_controls = (
                {obj.name.rsplit(" • ",1)[-1] for obj in island.faces} <= {"Object_100","Object_102"}
                and island.count in {944,2024} and .57 < low[2]
                and max(abs(low[0]),abs(high[0])) < .714
            )
            old_wheel_hardware = (
                (names == {"Object_100","Object_70"} and island.count == 40
                 and -.41 < low[0] < high[0] < -.23 and .055 < low[1] < high[1] < .110
                 and .700 < low[2] < high[2] < .800)
                or (names == {"Object_106"} and island.count == 1728
                    and -.365 < low[0] < high[0] < -.275 and .085 < low[1] < high[1] < .116
                    and .818 < low[2] < high[2] < .884)
            )
            if net or net_bar or seats_and_wheel or race_braces or old_door_controls or old_wheel_hardware:
                for obj, faces in island.faces.items():
                    removed.setdefault(obj, set()).update(faces)
    for obj, faces in removed.items():
        remove_faces(obj, faces)
    tub = bpy.data.objects["Object_114"]
    jamb_faces = set()
    for face in tub.data.polygons:
        x,y,z = face.center
        if abs(x) > .60 and -.558 < y < .532 and .420 < z < .827:
            jamb_faces.add(face.index)
    remove_faces(tub, jamb_faces)


def finish_door(door, m, side):
    card = MeshBatch(f"{door.name} inner stamping, upholstery and latch", door)
    # The skin curves inboard above its shoulder and narrows towards the bottom hem.
    edge = ((.759,-.585,.807),(.778,-.615,.770),(.813,-.631,.684),
            (.837,-.627,.533),(.819,-.613,.355),(.802,-.538,.296),
            (.783,.455,.296),(.793,.565,.337),(.815,.591,.425),
            (.831,.587,.606),(.800,.557,.736),(.746,.488,.803))
    inset = [(side*(x-.020), .99*y+.004, .985*(z-.55)+.55) for x,y,z in edge]
    card.loft(m.plastic, ([(side*x,y,z) for x,y,z in edge], inset), smooth=False)
    # The top, rear and front edges of the upholstery are inset from the painted hem.
    outline = ((-.587,.466),(-.527,.446),(.431,.446),(.521,.465),(.548,.531),
               (.533,.724),(.471,.785),(-.530,.790),(-.592,.759),(-.607,.690))
    face = [(side*.737,y,z) for y,z in outline]
    card.loft(m.leather, ([(side*.776, .993*y, z) for y,z in outline],face), smooth=False)
    pipe(card,m.hose,[(side*.742,y,z) for y,z in (*outline,outline[0])],.0035,segments=6)
    upper = ((-.561,.738),(-.505,.756),(.416,.756),(.486,.735),(.473,.712),(-.540,.713))
    card.panel(m.satin,[(side*.730,y,z) for y,z in upper],(side*.008,0,0))
    lower = ((-.554,.600),(-.514,.630),(.405,.630),(.484,.599),
             (.477,.491),(.426,.461),(-.495,.462),(-.562,.488))
    card.panel(m.insert,[(side*.728,y,z) for y,z in lower],(side*.011,0,0))
    pipe(card,m.seam,[(side*.726,y,z) for y,z in (*lower,lower[0])],.0016,segments=6)
    for z in (.475,.491,.507,.523,.539,.555,.571,.587):
        pipe(card,m.leather,[(side*.725,-.51,z),(side*.722,-.45,z),(side*.722,.40,z),
                             (side*.725,.45,z)],.0025,segments=5)
    rounded(card,m.leather,(side*.704,-.110,.674),(.061,.403,.065),.027)
    rounded(card,m.plastic,(side*.672,-.108,.672),(.011,.281,.029),.008)
    rounded(card,m.plastic,(side*.726,.209,.693),(.016,.146,.046),.015)
    pipe(card,m.chrome,[(side*.717,.247,.690),(side*.706,.218,.693),
                          (side*.703,.165,.698)],.005,segments=10)
    sweep(card,m.satin,((side*.735,.360,.674),(side*.706,.360,.674)),.022,segments=20)
    pipe(card,m.chrome,[(side*.704,.360,.674),(side*.691,.337,.659),
                          (side*.687,.304,.642)],.005,segments=10)
    sweep(card,m.plastic,((side*.694,.304,.642),(side*.673,.304,.642)),.010,segments=12)
    rounded(card,m.cast,(side*.770,-.604,.654),(.050,.020,.055),.006)
    rounded(card,m.steel,(side*.774,-.620,.653),(.030,.012,.026),.004)
    sweep(card,m.chrome,((side*.753,-.536,.785),(side*.753,-.536,.811)),.0049,segments=10)
    card.finish()


def fit_apertures(chassis, m):
    trim = MeshBatch("Carpeted footwells, rockers, door jambs and quarter trim", chassis)
    for side in (-1,1):
        # Build the carpet as a continuous tub into the firewall and rear footwell.
        profile = ((-.777,.449),(-.612,.451),(-.426,.452),(-.160,.452),(.160,.447),
                   (.338,.443),(.444,.463),(.507,.501),(.561,.594),(.565,.659))
        section = ((.132,.039),(.200,0),(.566,0),(.699,-.017),(.699,-.035),(.132,-.019))
        trim.loft(m.carpet,[[(side*x,y,z+height) for x,height in section] for y,z in profile],
                  smooth=False)
        rocker = ((.655,.385),(.688,.420),(.730,.432),(.772,.414),(.797,.369),(.770,.314),(.699,.319))
        trim.loft(m.plastic,[[(side*x,y,z) for x,z in rocker] for y in (-.627,-.585,.490,.559)])
        rounded(trim,m.satin,(side*.734,-.021,.436),(.057,.992,.008),.003,segments=2)
        for offset in (-.015,0,.015):
            sweep(trim,m.cast,((side*(.734+offset),-.478,.442),(side*(.734+offset),.440,.442)),.0011,segments=5)
        seal = ((.685,-.560,.813),(.700,-.614,.770),(.722,-.633,.655),
                (.733,-.625,.458),(.730,-.551,.430),(.729,.473,.430),
                (.711,.547,.470),(.703,.575,.597),(.699,.565,.737),(.682,.503,.830))
        pipe(trim,m.hose,[(side*x,y,z) for x,y,z in seal],.007,segments=8)
        kick = ((.388,.443),(.493,.458),(.553,.501),(.572,.637),(.555,.739),(.497,.768),(.410,.658))
        trim.panel(m.plastic,[(side*.691,y,z) for y,z in kick],(-side*.029,0,0))
        firewall = ((.196,.465),(.674,.472),(.690,.573),(.644,.776),(.510,.808),(.195,.735))
        trim.panel(m.carpet,[(side*x,.557,z) for x,z in firewall],(0,.028,0))
        rear = ((-.830,.402),(-.651,.411),(-.637,.491),(-.633,.726),(-.680,.795),(-1.240,.761),(-1.360,.538))
        trim.panel(m.plastic,[(side*.703,y,z) for y,z in rear],(-side*.037,0,0))
        pipe(trim,m.satin,[(side*.664,y,z) for y,z in ((-.655,.757),(-.709,.778),(-.939,.765),(-1.214,.741))],.0028,segments=6)
        rounded(trim,m.steel,(side*.729,-.632,.654),(.028,.018,.062),.007)
        pipe(trim,m.chrome,[(side*.733,-.616,.670),(side*.753,-.613,.668),
                             (side*.753,-.613,.639),(side*.733,-.616,.637)],.0045,segments=8)
        for z in (.470,.726):
            rounded(trim,m.cast,(side*.735,.598,z),(.067,.072,.041),.008)
            sweep(trim,m.steel,((side*.811,.690,z-.020),(side*.811,.690,z+.019)),.009,segments=12)
    rounded(trim,m.carpet,(0,-.035,.474),(.303,1.208,.113),.056)
    trim.finish()


def finish_seats(chassis,m):
    build_seats(chassis,m,1)
    bolsters = MeshBatch("Shaped seat bolsters, welt seams and recliner hardware",chassis)
    for center in (-.36,.36):
        for side in (-1,1):
            for y in (-.386,-.055):
                rounded(bolsters,m.plastic,(center+side*.170,y,.461),(.053,.070,.036),.007,segments=2)
            cushion = [(center+side*x,y,z) for x,y,z in
                       ((.168,.011,.586),(.188,-.046,.618),(.192,-.151,.632),
                        (.192,-.302,.638),(.184,-.380,.631),(.163,-.423,.603))]
            back = [(center+side*x,y,z) for x,y,z in
                    ((.154,-.365,.631),(.182,-.367,.689),(.196,-.383,.771),
                     (.181,-.414,.878),(.149,-.455,.943))]
            sweep(bolsters,m.leather,cushion,(.022,.028,.030,.030,.027,.016),segments=12)
            sweep(bolsters,m.leather,back,(.013,.026,.030,.029,.021),segments=12)
            pipe(bolsters,m.seam,[(x-side*.008,y,z+rise) for (x,y,z),rise in
                                 zip(cushion,(.020,.026,.028,.028,.026,.014),strict=True)],.0011,segments=5)
            pipe(bolsters,m.seam,[(x-side*.012,y-depth,z) for (x,y,z),depth in
                                 zip(back,(.010,.022,.026,.025,.017),strict=True)],.0011,segments=5)
        outer = -1 if center < 0 else 1
        rounded(bolsters,m.plastic,(center+outer*.218,-.379,.528),(.023,.124,.093),.022)
        sweep(bolsters,m.cast,((center+outer*.227,-.404,.542),
                               (center+outer*.245,-.404,.542)),.026,segments=18)
    bolsters.finish()


def cabin(chassis, panels, m):
    clean_race_cabin(chassis)
    steering = pivot("SteeringWheel", (-.357,.308,.844), chassis)
    panels["SteeringWheel"] = steering
    fit_apertures(chassis,m)
    for sign in (-1,1):
        door=panels[f"Door_{'L' if sign<0 else 'R'}"]
        finish_door(door,m,sign)
    column = MeshBatch("Steering column extension and knee bolster", chassis)
    sweep(column,m.hose,((-.357,.330,.844),(-.356,.446,.835)),.027,segments=18)
    rounded(column,m.plastic,(-.345,.436,.667),(.51,.079,.051),.022)
    column.finish()
    ivory=pbr("Ivory dial faces", (.64,.63,.55), .44)
    dark=pbr("Charcoal dial marks", (.028,.028,.026), .63, emission=.04)
    build_dash(chassis,replace(m,lens=ivory,dash_glow=dark),1,fascia=m.satin)
    dash=bpy.data.objects["Twin-cowl dash, instruments and glovebox"]
    for vertex in dash.data.vertices:
        vertex.co.y-=.070
        vertex.co.z-=.086
    dash.data.update()
    finish_seats(chassis,m)
    build_steering(chassis,steering,m,1)
    build_cabin_hardware(chassis,m)


def mirrors(panels, m):
    for name, sign in (("L",-1),("R",1)):
        door=panels[f"Door_{name}"]
        for obj in tuple(door.children):
            if (obj.name.endswith("chrome • Object_72") or obj.name.endswith("mirror • Object_118")
                    or obj.name.endswith("black • Object_22")):
                bpy.data.objects.remove(obj, do_unlink=True)
        assembly=MeshBatch(f"{name} rectangular mirror with indicator",door)
        x=sign*.82
        rounded(assembly,m.chrome,(x,.411,.879),(.144,.072,.082),.025)
        rounded(assembly,bpy.data.materials["Silvered mirror faces"],(x,.374,.878),(.129,.008,.065),.021)
        pipe(assembly,m.chrome,[(sign*.754,.427,.791),(sign*.779,.420,.843),(x,.418,.849)],.0135,segments=10)
        indicator=bpy.data.materials[f"RearIndicator_{name}"]
        for step in range(-3,4):
            dx=sign*(.039-abs(step)*.007)
            sweep(assembly,indicator,((x+dx,.370,.878+step*.007),(x+dx,.366,.878+step*.007)),.0029,segments=8)
        assembly.finish()


def trunk(chassis, lid, m):
    oxblood=pbr("Oxblood trunk lining", (.122,.026,.019), .82)
    edge=pbr("Oxblood trim piping", (.157,.037,.028), .60)
    build_trunk(chassis,lid,replace(m,carpet=oxblood,leather=edge,plastic=oxblood),1)
    hinge=MeshBatch("Deck lid hinges, inner pressing and weather seal",lid)
    liners=MeshBatch("Trunk bulkhead piping and hinge brackets",chassis)
    for side in (-1,1):
        x=side*.50
        pipe(hinge,m.cast,[(x,-1.786,.895),(x,-1.866,.876),(x,-1.935,.843),(x,-2.008,.824)],.013,segments=11)
        rounded(hinge,m.cast,(x,-1.938,.831),(.064,.083,.018),.012)
        rounded(liners,m.cast,(x,-1.770,.774),(.070,.060,.145),.015)
        for y in (-2.157,-1.67):
            x2=side*(.52 if y < -2 else .58)
            sweep(liners,edge,((x2,y,.785),(x2,y,.812)),.022,segments=12)
    pipe(hinge,m.hose,[(-.542,-1.80,.84),(-.532,-2.165,.814),(0,-2.19,.824),
        (.532,-2.165,.814),(.542,-1.8,.84)],.006,segments=8)
    for x in (-.31,.31):
        rounded(hinge,m.cast,(x,-1.999,.825),(.281,.26,.018),.046)
    rounded(hinge,m.steel,(0,-2.16,.803),(.060,.058,.028),.008)
    for x in (-.364,-.290,-.215,.215,.29,.364):
        rounded(liners,edge,(x,-1.617,.668),(.008,.012,.206),.003)
    rounded(liners,oxblood,(0,-2.169,.746),(.184,.078,.077),.017)
    liners.finish()
    hinge.finish()


def build_restomod(chassis, panels):
    materials=finishes(2)
    surface = materials.leather.node_tree
    texture = surface.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images["Charcoal interior Normal"]
    normal = surface.nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = .38
    surface.links.new(texture.outputs["Color"],normal.inputs["Color"])
    surface.links.new(normal.outputs["Normal"],surface.nodes.get("Principled BSDF").inputs["Normal"])
    cabin(chassis,panels,materials)
    mirrors(panels,materials)
    engine_bay(chassis,materials)
    underbody(chassis,materials)
    trunk(chassis,panels["Trunk"],materials)
