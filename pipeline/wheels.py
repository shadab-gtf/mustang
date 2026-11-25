from math import cos, pi, sin

from body import FRONT_AXLE, REAR_AXLE, WHEEL_X, count, grid
from geometry import box, lathe, panel, sample

WHEEL_SPECS = {
    "FL": (-WHEEL_X, FRONT_AXLE, .32705, .245),
    "FR": ( WHEEL_X, FRONT_AXLE, .32705, .245),
    "RL": (-WHEEL_X, REAR_AXLE, .33755, .275),
    "RR": ( WHEEL_X, REAR_AXLE, .33755, .275),
}


def tire(name, center, radius, width, ctx):
    half=width/2
    body = [(-1,.257),(-1,.276),(-.979,.292),(-.942,radius-.020),
            (-.858,radius-.010),(-.761,radius-.0035),(-.668,radius-.0013),
            (.668,radius-.0013),(.761,radius-.0035),(.858,radius-.010),
            (.942,radius-.020),(.979,.292),(1,.276),(1,.257),(.925,.238),(-.925,.238)]
    sweep = body[:6]
    sweep += [(u,sample(body[:-2],u)[0]) for u in grid(-.69,.69,count(ctx.detail,38,11))]
    sweep += body[-7:]
    p, m = ctx.wheels[name],ctx.materials

    def tread(axial, angle):
        normalized = axial/half
        if abs(normalized) > .93:
            return 0
        shoulder = min(1,max(0,(.93-abs(normalized))/.30))
        channels = max(max(0, 1-abs(normalized-v)/.049) for v in (-.54,-.23,.23,.54))
        chevron=abs(sin((angle*22 + 3.8*abs(normalized) + .9*normalized)))
        blocks = max(0,1-chevron/.44)
        return -.0038*max(channels, blocks*.66)*shoulder

    lathe("Directional radial tire "+name,center,[(u*half,r) for u,r in sweep],0,m["rubber"],p,
          segments=(224,112,68,36)[ctx.detail], radius_offset=tread if ctx.detail <= 1 else None)
    if ctx.detail < 2:
        side = 1 if center[0]>0 else -1
        for r in (.263,.288,radius-.033):
            offset=side*(half * (1 if r < .278 else .982))
            lathe("Molded tire shoulder band "+name,center,
                  [(offset-.001,r-.001),(offset+.001,r-.001),
                   (offset+.001,r+.001),(offset-.001,r+.001)],0,m["rubber"],p,segments=80)


def wheels(ctx):
    m=ctx.materials
    for key, (x,y,radius,width) in WHEEL_SPECS.items():
        center=(x,y,radius)
        side = 1 if x>0 else -1
        half = width/2
        p, fixed=ctx.wheels[key],ctx.knuckles[key]
        segments = count(ctx.detail,100,28)
        tire(key,center,radius,width,ctx)
        outer=half-.006
        lathe("Spun wheel barrel "+key,center,[(u,r) for u,r in [
            (-half+.008,.240),(outer-.003,.240),(outer-.001,.231),
            (outer-.013,.221),(-half+.011,.221)]],0,m["wheel"],p,segments=segments)
        lip = [(-.029,.222),(-.023,.232),(-.016,.239),(-.006,.245),(.001,.243),
               (.002,.239),(-.003,.236),(-.012,.232),(-.018,.225),(-.022,.222)]
        lathe("Diamond cut rim lip "+key,center,[(side*(outer+u),r) for u,r in lip],0,m["chrome"],p,segments=segments)
        lathe("Forged hub "+key,center,[(side*(outer+u),r) for u,r in
              [(-.045,.081),(-.037,.088),(-.016,.081),(-.014,.062),(-.006,.056),
               (-.006,.026),(-.039,.022)]],0,m["wheel"],p,segments=segments)
        rotor_x=side*(outer-.071)
        lathe("Vented brake rotor "+key,center,[(rotor_x+u,r) for u,r in
              [(-.012,.070),(-.012,.158),(-.009,.174),(.008,.174),(.011,.169),
               (.011,.091),(.025,.078),(.027,.060)]],0,m["disc"],p,segments=segments)
        lathe("Center cap "+key,center,[(side*(outer+u),r) for u,r in
              [(-.009,.017),(-.008,.026),(.005,.026),(.008,.021),(.007,.0006),(-.008,.0006)]],
              0,m["alloy"],p,segments=segments)
        for spoke in range(7):
            angle=spoke*2*pi/7
            profile = [(.069,.021,-.016),(.093,.023,-.006),(.134,.019,-.007),
                       (.192,.013,-.022),(.216,.019,-.033),(.227,.020,-.033)]
            rows=[]
            for r in grid(.069,.227,count(ctx.detail,14,5)):
                width_spoke, recess=sample(profile,r)
                row=[]
                for t in grid(-1,1,6 if ctx.detail<=1 else 3):
                    phase=angle+((r-.069)*.21+t*width_spoke)/r
                    bulge=.006*(1-abs(t)**3)
                    row.append((x+side*(outer+recess+bulge),y+r*cos(phase),radius+r*sin(phase)))
                rows.append(row)
            panel("Forged spoke "+key,rows,m["wheel"],p,thickness=(-side*.016,0,0))
        for lug in range(5):
            phase=lug*2*pi/5
            anchor=(x+side*(outer-.006),y+.043*cos(phase),radius+.043*sin(phase))
            lathe("Hexagonal lug "+key,anchor,[(side*u,r) for u,r in
                  [(-.004,.0078),(.004,.0078),(.008,.0053),(.008,.001),(-.004,.001)]],
                  0,m["alloy"],p,segments=6)
        if ctx.detail < 2:
            for item in range(28):
                phase=item*2*pi/28
                anchor=(x+side*(outer-.016),y+.226*cos(phase),radius+.226*sin(phase))
                lathe("Rim assembly fastener "+key,anchor,[(0,.0029),(side*.004,.0029),
                      (side*.004,.0005),(0,.0005)],0,m["alloy"],p,segments=7)
        for index,offset in enumerate((-.046,.009,.056)):
            box("Radial brake caliper "+key,(x+rotor_x+side*.022,y-.145+offset*.22,radius+offset),
                (.077,.058,.055),m["caliper"],fixed,radius=.014,segments=3)
