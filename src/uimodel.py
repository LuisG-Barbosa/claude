import json

def load(path, viewkey):
    with open(path) as f: d=json.load(f)
    um = json.loads(d["editorSettings"][viewkey]["uiModel"])
    return d, um, um["contents"]

QUERY_NODE_CLASSES = {
    "sap.cdw.querybuilder.Entity",
    "sap.cdw.querybuilder.RenameElements",
    "sap.cdw.querybuilder.CalculatedElements",
    "sap.cdw.querybuilder.AggregatedElements",
    "sap.cdw.querybuilder.Filter",
    "sap.cdw.querybuilder.Join",
    "sap.cdw.querybuilder.Union",
    "sap.cdw.querybuilder.Output",
}

def build_index(contents):
    """Return:
       owner_of_elem: element_uuid -> (owner_uuid, owner_class, owner_name)
       nodes: uuid -> node (only query nodes)
       elems: uuid -> element node (classDefinition Element)
    """
    owner_of_elem = {}
    nodes = {}
    elems = {}
    for uid, node in contents.items():
        if not isinstance(node, dict): continue
        cd = node.get("classDefinition")
        if cd in QUERY_NODE_CLASSES:
            nodes[uid] = node
            for euid in node.get("elements", {}):
                owner_of_elem[euid] = (uid, cd, node.get("name"))
        if cd == "sap.cdw.querybuilder.Element":
            elems[uid] = node
    return owner_of_elem, nodes, elems

def short(c): return c.split(".")[-1] if c else c
