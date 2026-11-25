from math import cos, pi, sin, sqrt

from geometry import box, lathe, panel, plate, sample, tube

FRONT_AXLE = 1.3716
REAR_AXLE = -1.3716
WHEEL_X = .805

# Y, half width at the belt, belt height, centerline height.
BELT = (
    (-2.285,.717,.797,.813), (-2.205,.807,.827,.837), (-1.93,.854,.848,.854),
    (-1.55,.868,.865,.867), (-1.24,.859,.860,.863), (-.86,.812,.824,.834),
    (-.48,.803,.811,.828), (.14,.808,.814,.838), (.58,.816,.829,.859),
    (.81,.828,.844,.875), (1.18,.863,.853,.893), (1.47,.884,.848,.889),
    (1.93,.850,.811,.858), (2.16,.810,.772,.817), (2.255,.745,.754,.792),
)


def count(detail, high, minimum):
    return max(minimum, high // (detail + 1))


def grid(first, last, intervals):
    return [first + i*(last-first)/intervals for i in range(intervals+1)]


def top(y, x):
    width, belt, center = sample(BELT, y)
    fraction = abs(x)/width
    broad = center + (belt-center)*fraction**2
    hood_bulge = max(0, 1-(abs(x)/.45)**2)**1.1
    hood_length = max(0, min((y-.76)/.28, (2.11-y)/.34, 1))
    return broad + .027*hood_bulge*hood_length


def shoulder(y, side, height):
    width, z, _ = sample(BELT, y)
    lower = .366
    t = (height-lower)/(z-lower)
    swell = .041*sin(pi*max(0, min(t, 1))) - .024*(1-t)**2
    front = .036*max(0, 1-((y-FRONT_AXLE)/.59)**2)**2
    rear = .045*max(0, 1-((y-REAR_AXLE)/.54)**2)**2
    return side*(width+swell+(front+rear)*sin(pi*max(0, min(t, 1)))**.8)


def arch_bottom(y):
    axle = FRONT_AXLE if y > 0 else REAR_AXLE
    t = (y-axle)/(.395 if y > 0 else .410)
    return .361+.383*sqrt(max(0, 1-t*t)) if abs(t) < 1 else .361


def skin(ctx, first, last, side, parent, material, name, *, wheel_cut=False):
    ys = grid(first, last, count(ctx.detail, 68 if wheel_cut else 44, 13))
    if wheel_cut:
        axle = FRONT_AXLE if first > 0 else REAR_AXLE
        aperture = .395 if first > 0 else .410
        ys += [axle + aperture * sin(angle) for angle in grid(-pi/2, pi/2, count(ctx.detail, 34, 12))]
        ys = sorted(set(y for y in ys if first <= y <= last))
    rows = []
    for y in ys:
        _, upper, _ = sample(BELT, y)
        lower = arch_bottom(y) if wheel_cut else .370
        rows.append([(shoulder(y, side, z), y, z) for z in grid(lower, upper, count(ctx.detail, 12, 4))])
    panel(name, rows, material, parent, thickness=(-side*.011, 0, 0))
    return rows


def deck(ctx, name, y0, y1, limits, parent, *, stripes=True):
    mats = ctx.materials
    ys = grid(y0, y1, count(ctx.detail, 47, 15))
    rows = [[(x,y,top(y,x)) for x in grid(*limits(y), count(ctx.detail,40,10))] for y in ys]
    panel(name, rows, mats["paint"], parent)
    if stripes:
        for side in (-1, 1):
            bounds = sorted((side*.030, side*.241))
            rows = [[(x,y,top(y,x)+.0016) for x in grid(*bounds, count(ctx.detail, 7, 3))] for y in ys]
            panel(name+" | stripe", rows, mats["stripe"], parent, thickness=(0,0,-.0009))


def glass_panel(ctx, name, rows, parent, *, depth=(0,0,-.004), trim=True):
    mats = ctx.materials
    panel(name, rows, mats["glass"], parent, thickness=depth)
    if trim:
        perimeter = rows[0] + [row[-1] for row in rows[1:]] + list(reversed(rows[-1][:-1]))
        perimeter += [row[0] for row in reversed(rows[1:-1])]
        tube(name+" | seal", perimeter, .009, mats["dark"], parent, closed=True, sides=6)
        outer = [(x,y,z+.006) for x,y,z in perimeter]
        tube(name+" | stainless reveal", outer, .0038, mats["chrome"], parent, closed=True, sides=6)


def greenhouse(ctx):
    p, m = ctx.root, ctx.materials
    roof = [(-.675,.626,1.233,1.269), (-.53,.659,1.260,1.299),
            (-.30,.671,1.272,1.3157), (-.11,.668,1.270,1.309), (.064,.632,1.245,1.285)]

    def roof_surface(y, x):
        width, edge, crown = sample(roof,y)
        return crown-(crown-edge)*(abs(x)/width)**2.6

    ys = grid(roof[0][0],roof[-1][0],count(ctx.detail,34,12))
    panel("Fastback roof pressing", [[(x,y,roof_surface(y,x)) for x in
          grid(-sample(roof,y)[0],sample(roof,y)[0],count(ctx.detail,30,10))] for y in ys],m["paint"],p)
    for side in (-1, 1):
        panel("Fastback roof stripe", [[(x,y,roof_surface(y,x)+.0015) for x in
              grid(*sorted((side*.030,side*.241)),6)] for y in ys],m["stripe"],p,thickness=(0,0,-.0009))

    forward = [(.071,.627,1.248,1.278), (.32,.683,1.050,1.085), (.658,.733,.844,.866)]
    back = [(-1.687,.566,.876,.898), (-1.39,.595,.935,.958),
            (-1.07,.600,1.052,1.077), (-.70,.605,1.230,1.263)]
    for name, profile in (("Laminated windshield",forward),("Fastback rear glass",back)):
        rows = []
        for y in grid(profile[0][0],profile[-1][0],count(ctx.detail,26,9)):
            width, edge, crown = sample(profile,y)
            rows.append([(x,y,crown-(crown-edge)*(x/width)**2) for x in grid(-width,width,count(ctx.detail,30,10))])
        glass_panel(ctx,name,rows,p)

    for side in (-1,1):
        rail_top = [(side*sample(roof,y)[0],y,sample(roof,y)[1]) for y in ys]
        rail_front = [(side*.733,.661,.847),(side*.713,.50,.949),(side*.682,.32,1.055),
                      (side*.65,.15,1.18),(side*.632,.066,1.248)]
        tube("Painted A pillar",rail_front,.024,m["paint"],p,sides=12)
        tube("Roof drip rail", rail_front + list(reversed(rail_top[:-1])),.008,m["chrome"],p,sides=9)
        # The C pillar follows the rear window above the swept rear quarter.
        ys_back = grid(-1.804,-.592,count(ctx.detail,33,12))
        pillar_stations = [(-1.804,.612,.866),(-1.64,.574,.905),(-1.38,.601,.951),
                           (-1.06,.608,1.064),(-.83,.611,1.178),(-.69,.621,1.244),
                           (-.592,.646,1.260)]
        def sail_point(y,t,offset=0):
            inner_x, inner_z=sample(pillar_stations,y)
            outer_y=y-.09*max(0,(y+1.30)/.708)
            outer_x, outer_z, _ = sample(BELT,outer_y)
            return (side*((outer_x-.006)*(1-t)+inner_x*t+.014*sin(pi*t)+offset),
                    outer_y+(y-outer_y)*t,
                    (outer_z+.007)*(1-t)+inner_z*t+.013*sin(pi*t)+offset)
        rows = [[sail_point(y,t) for t in grid(0,1,13)] for y in ys_back]
        panel("Stamped fastback sail panel",rows,m["paint"],p,thickness=(0,0,-.012))
        outline = [sail_point(y,t,.006) for y,t in
                   [(-1.026,.38),(-.80,.40),(-.747,.77),(-.782,.85),(-1.023,.81)]]
        panel("Sail scoop opening",[[sail_point(y,t,.008) for t in grid(.42,.80,5)]
              for y in grid(-1.019,-.796,9)],m["dark"],p,thickness=(-side*.004,0,0))
        tube("Sail scoop painted rolled edge",outline,.009,m["paint"],p,sides=9,closed=True)
        if ctx.detail <= 1:
            for y in grid(-.994,-.817,4):
                tube("Sail scoop baffle",[sail_point(y,t,.012) for t in grid(.48,.75,5)],
                     .003,m["dark"],p,sides=5)


def door_equipment(ctx, side, key):
    p, m = ctx.doors[key], ctx.materials
    # Frameless glass is nested in the door and moves within its guides.
    upper = [(-.69,.659,1.224),(-.55,.669,1.247),(-.24,.669,1.259),
             (.054,.650,1.229),(.26,.690,1.090),(.529,.751,.853)]
    rows = []
    for y in grid(-.683,.523,count(ctx.detail,26,9)):
        crown_x,crown_z = sample(upper,y)
        rows.append([(side*(.788+(crown_x-.788)*t+.021*sin(pi*t)),y,
                      .804+(crown_z-.804)*t) for t in grid(0,1,count(ctx.detail,12,4))])
    glass_panel(ctx,"Tempered side glass "+key,rows,ctx.windows[key],depth=(-side*.004,0,0),trim=False)
    tube("Window belt molding "+key,[(shoulder(y,side,sample(BELT,y)[1])+side*.005,
         y,sample(BELT,y)[1]+.002) for y in grid(-.76,.55,23)],.0052,m["chrome"],p,sides=8)

    handle_y, handle_z = -.630,.772
    handle_x = shoulder(handle_y,side,handle_z)
    box("Outside handle recess "+key,(handle_x+side*.003,handle_y,handle_z),(.012,.152,.036),m["dark"],p,radius=.012)
    tube("Chrome door handle "+key,[(handle_x+side*.009,handle_y-.067,handle_z),
         (handle_x+side*.026,handle_y-.047,handle_z+.008),
         (handle_x+side*.025,handle_y+.043,handle_z+.008),
         (handle_x+side*.009,handle_y+.063,handle_z)],.008,m["chrome"],p)
    lathe("Door lock "+key,(handle_x+side*.009,handle_y-.092,handle_z-.024),
          [(-.003,.008),(.004,.008),(.005,.004),(-.003,.004)],0,m["chrome"],p,segments=14)
    mirror_anchor = (side*.789,.478,.830)
    tube("Mirror stem "+key,[mirror_anchor,(side*.845,.479,.873),(side*.909,.464,.899)],
         .013,m["chrome"],p,sides=12)
    box("Mirror shell "+key,(side*.943,.469,.915),(.143,.066,.067),m["chrome"],p,radius=.028,segments=4)
    box("Mirror face "+key,(side*.942,.433,.915),(.126,.009,.054),m["alloy"],p,radius=.008)


def lower_trim(ctx, start, end, side, parent):
    m = ctx.materials
    ys = grid(start,end,count(ctx.detail,24,7))
    for bottom, top_z in ((.434,.460),(.466,.473)):
        panel("Rocker stripe", [[(shoulder(y,side,z)+side*.0018,y,z) for z in (bottom,top_z)]
              for y in ys],m["stripe"],parent,thickness=(-side*.0008,0,0))


def build_body(ctx):
    p, m = ctx.root, ctx.materials
    for side, key in ((-1,"L"),(1,"R")):
        front = skin(ctx,.593,2.255,side,p,m["paint"],"Front fender "+key,wheel_cut=True)
        rear = skin(ctx,-2.285,-.802,side,p,m["paint"],"Rear quarter "+key,wheel_cut=True)
        skin(ctx,-.795,.586,side,ctx.doors[key],m["paint"],"Door skin "+key)
        for rows, axle, label in ((front,FRONT_AXLE,"Front"),(rear,REAR_AXLE,"Rear")):
            lip = [row[0] for row in rows if abs(row[0][1]-axle) < .402]
            tube(label+" rolled wheel opening "+key,lip,.010,m["paint"],p,sides=9)
            inner = [[(a,b,c),(a-side*.148,b,c+.028),(a-side*.224,b,c+.053)] for a,b,c in lip]
            panel(label+" inner wheel liner "+key,inner,m["dark"],p,thickness=(0,0,.006))
        rocker_top = [(shoulder(y,side,.369)-side*.016,y,.369) for y in grid(-.891,.899,24)]
        tube("Rolled rocker lip "+key,rocker_top,.021,m["dark"],p,sides=10)
        lower_trim(ctx,-.795,.586,side,ctx.doors[key])
        lower_trim(ctx,.594,.964,side,p)
        lower_trim(ctx,-.955,-.802,side,p)
        def fender_limits(y):
            w = sample(BELT,y)[0]
            return sorted((side*.656,side*w))
        deck(ctx,"Front fender crown "+key,.656,2.255,fender_limits,p,stripes=False)
        def quarter_limits(y):
            w=sample(BELT,y)[0]
            return sorted((side*.613,side*w))
        deck(ctx,"Quarter panel crown "+key,-2.285,-1.454,quarter_limits,p,stripes=False)
        def shoulder_limits(y):
            w=sample(BELT,y)[0]
            return sorted((side*.721,side*w))
        deck(ctx,"Sail panel lower shoulder "+key,-1.462,-.803,shoulder_limits,p,stripes=False)
        door_equipment(ctx,side,key)
        scoop = [(shoulder(y,side,z)+side*.009,y,z)
                 for y,z in [(-1.008,.598),(-1.104,.738),(-.947,.754),(-.924,.542)]]
        plate("Quarter intake recess "+key,scoop,m["dark"],p,depth=(-side*.012,0,0),radius=.013)
        tube("Quarter intake rim "+key,scoop,.011,m["paint"],p,closed=True,sides=9)

    deck(ctx,"Stamped hood",.722,2.249,lambda y:(-.650,.650),ctx.hood)
    deck(ctx,"Cowl panel",.654,.715,lambda y:(-.650,.650),p)
    deck(ctx,"Deck lid",-2.276,-1.693,lambda y:(-.609,.609),ctx.trunk)
    deck(ctx,"Rear glass sill",-1.686,-1.619,lambda y:(-.565,.565),p,stripes=False)
    if ctx.detail < 2:
        for sx in (-1,1):
            for index in range(11):
                x=sx*(.248+index*.028)
                box("Cowl vent slot",(x,.692,top(.692,x)+.002),(.012,.024,.003),m["black"],p,radius=.002)
            wiper = [(sx*.627,.645,.876), (sx*.444,.599,.896),(sx*.216,.572,.927)]
            tube("Windshield wiper arm",wiper,.006,m["dark"],p,sides=8)
            tube("Windshield wiper blade",[(sx*.434,.592,.901),(sx*.111,.546,.939)],
                 .0064,m["dark"],p,sides=7)
            tube("Hood leading recess lip",[(sx*.237,2.247,top(2.247,.237)),
                 (sx*.425,2.241,top(2.241,.425)),(sx*.626,2.245,top(2.245,.626))],.0033,m["dark"],ctx.hood)
    greenhouse(ctx)
