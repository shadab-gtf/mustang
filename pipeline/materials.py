import bpy
import numpy as np


def pbr(name, color, roughness, metallic=0, *, coat=0, emission=0, transmission=0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    for key, value in {
        "Base Color": (*color, 1), "Roughness": roughness, "Metallic": metallic,
        "Coat Weight": coat, "Coat Roughness": .19, "Transmission Weight": transmission,
        "IOR": 1.19 if transmission else 1.5, "Emission Color": (*color, 1),
        "Emission Strength": emission,
    }.items():
        shader.inputs[key].default_value = value
    return material


def detail_maps(material, size, seed, roughness, variation, bump):
    rng = np.random.default_rng(seed)
    grain = rng.random((size, size), dtype=np.float32)
    grain = (grain * 2 + np.roll(grain, 1, 0) + np.roll(grain, 1, 1)) / 4 - .5
    pixels = np.ones((size, size, 4), dtype=np.float32)
    tree = material.node_tree
    shader = tree.nodes.get("Principled BSDF")

    def image_node(suffix):
        image = bpy.data.images.new(material.name + suffix, size, size)
        image.colorspace_settings.name = "Non-Color"
        image.pixels.foreach_set(pixels.ravel())
        image.update()
        image.pack()
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        return node

    pixels[:, :, :3] = (roughness + variation * grain)[:, :, None]
    rough = image_node(" Roughness")
    rough.location = (-540, 120)
    tree.links.new(rough.outputs["Color"], shader.inputs["Roughness"])
    pixels[:, :, 0] = .5 + bump * (np.roll(grain, 1, 1) - np.roll(grain, -1, 1))
    pixels[:, :, 1] = .5 - bump * (np.roll(grain, 1, 0) - np.roll(grain, -1, 0))
    pixels[:, :, 2] = .5 + np.sqrt(np.maximum(0, .25 - (pixels[:, :, 0]-.5)**2 - (pixels[:, :, 1]-.5)**2))
    texture = image_node(" Normal")
    texture.location = (-550, -170)
    normal = tree.nodes.new("ShaderNodeNormalMap")
    normal.location = (-260, -165)
    tree.links.new(texture.outputs["Color"], normal.inputs["Color"])
    tree.links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return normal


def vehicle_materials(detail):
    materials = {}
    for key, name, color, rough, metal, coat, emission, transmission in [
        ("paint", "Moss green metallic", (.018,.036,.024), .31,.55,.34,0,0),
        ("stripe", "Warm ivory racing stripes", (.73,.76,.68), .32,.08,.38,0,0),
        ("dark", "Black satin trim", (.019,.021,.020), .43,.27,0,0,0),
        ("rubber", "Tire sidewall rubber", (.023,.025,.026), .56,0,0,0,0),
        ("chrome", "Polished brightwork", (.73,.77,.80), .19,.95,.19,0,0),
        ("alloy", "Satin machined aluminum", (.44,.49,.53), .29,.87,0,0,0),
        ("wheel", "Forged gunmetal spokes", (.101,.115,.124), .31,.79,.18,0,0),
        ("disc", "Ground steel rotor", (.24,.25,.25), .37,.87,0,0,0),
        ("caliper", "Graphite cast caliper", (.135,.14,.137), .48,.53,0,0,0),
        ("glass", "Automotive safety glass", (.86,.94,.93), .075,0,0,0,.99),
        ("lens", "Fluted clear lamp lens", (.70,.79,.85), .14,0,0,0,.64),
        ("red", "Red acrylic lens", (.36,.008,.012), .24,.12,.40,0,0),
        ("black", "Grille and radiator shadow", (.007,.010,.010), .68,.13,0,0,0),
        ("low", "HeadlightEmission", (.62,.71,.81), .24,.25,0,1.6,0),
        ("high", "HighBeamEmission", (.82,.91,.99), .21,.2,0,2.5,0),
        ("tail", "TailEmission", (.48,.010,.012), .25,.15,.29,.65,0),
        ("brake", "BrakeEmission", (.57,.013,.015), .25,.15,.29,2.2,0),
        ("reverse", "ReverseEmission", (.62,.73,.68), .25,.18,.12,.9,0),
    ]:
        materials[key] = pbr(name, color, rough, metal, coat=coat, emission=emission, transmission=transmission)
    for side in ("L", "R"):
        for end in ("Front", "Rear"):
            color = (.72,.21,.008) if end == "Front" else (.54,.018,.012)
            materials[end+side] = pbr(f"{end}Indicator_{side}", color, .24, .12, coat=.26, emission=1.5)
    if detail < 2:
        size = 2048 if detail == 0 else 512
        detail_maps(materials["paint"], size, 67, .31, .055, .055)
        detail_maps(materials["rubber"], size, 23, .56, .18, .25)
    return materials
