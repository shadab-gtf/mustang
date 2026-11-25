from math import radians

from wheels import WHEEL_SPECS


def track(obj, name, channel, axis, base, poses, start, *, linear=False):
    obj.animation_data_create()
    for frame, displacement in poses:
        getattr(obj,channel)[axis] = base+displacement
        obj.keyframe_insert(data_path=channel,index=axis,frame=frame,group=name)
    data = obj.animation_data
    action = data.action
    action.name = f"{name} · {obj.name}"
    for curve in action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR" if linear else "BEZIER"
            key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"
    slot = data.action_slot
    data.action = None
    getattr(obj,channel)[axis] = base
    parent_track = data.nla_tracks.new()
    parent_track.name = name
    strip = parent_track.strips.new(name,start,action)
    strip.action_slot = slot
    strip.extrapolation = "HOLD"


def motion(dist, end=77):
    return [(1,0),(25,dist),(51,dist),(end,0)]


def build_tracks(ctx, markers):
    for side,key in ((-1,"L"),(1,"R")):
        door=ctx.doors[key]
        window=ctx.windows[key]
        track(door,"Doors","rotation_euler",2,0,motion(side*radians(62)),83)
        # Use one NLA strip per transform with X/Y travel keyed onto the same action.
        for frame, y_delta in motion(-.422):
            window.location.x=side*.040*y_delta/-.422
            window.keyframe_insert(data_path="location",index=0,frame=frame,group="Windows")
        track(window,"Windows","location",2,window.location.z,motion(-.422),1)
    track(ctx.hood,"Hood","rotation_euler",0,0,motion(radians(54)),165)
    track(ctx.trunk,"Trunk","rotation_euler",0,0,motion(radians(-52)),247)
    for key,(_,_,radius,_) in WHEEL_SPECS.items():
        track(ctx.wheels[key],"Wheel_Rotation","rotation_euler",0,0,
              [(1,0),(25,-6.2831853),(49,-12.5663706)],451,linear=True)
        track(ctx.suspension[key],"Suspension","location",2,radius,
              [(1,0),(18,.055),(36,-.024),(56,.033),(73,0)],370)
    steering=[(1,0),(21,radians(25)),(48,radians(-26)),(74,0)]
    for key in ("FL","FR"):
        track(ctx.knuckles[key],"Steering","rotation_euler",2,0,steering,324)
    track(ctx.steering,"Steering","rotation_euler",1,0,[(frame,-value*10.7) for frame,value in steering],324)
    vibration=[(1,0)]+[(frame,.007*(-1)**frame) for frame in range(2,29)]+[(29,0)]
    track(ctx.engine,"Engine_Idle","rotation_euler",1,0,vibration,500,linear=True)
    for name, frame in (
        ("Windows",1),("Doors",83),("Hood",165),("Trunk",247),
        ("Steering",324),("Suspension",370),("Wheel rotation",451),("Engine idle",500)
    ):
        markers.new(name,frame=frame)
