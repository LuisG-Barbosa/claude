#!/usr/bin/env python3
"""
Construye 3VR_INVBALANCEFOROBSMAT_01 como VISTA GRAFICA por poda-e-injerto:
parte de 2VR_SCM_INVBALANCE_01 enriquecido (A_1), poda el subgrafo del calculo
base (ancestros de Projection 14) y lo reemplaza por un Entity que lee el
2VR_SCM_INVBALANCE_01 ORIGINAL. Conserva intacta la capa de enriquecimiento.
Quita del downstream las 14 columnas que el 2VR original no expone.
Edita uiModel + query CSN + definitions de forma consistente.
"""
import json, sys, copy
sys.path.insert(0, "src")
import uimodel as U

SRC = "input/invbalance/INVBALANCE_A_1.json"
SRC_VIEW = "2VR_SCM_INVBALANCE_01"
NEW_VIEW = "3VR_INVBALANCEFOROBSMAT_01"
BASE_REF = "2VR_SCM_INVBALANCE_01"          # fuente que consumira (el original)
OUT_JSON = f"output/{NEW_VIEW}.json"

DROP = {  # columnas que P14 pasa pero el 2VR original NO expone -> quitar del downstream
 "PrevMonth2StockCnsmpnValueInCC","PrevMonth2StockCnsmpnValueInGC","PrevMonthStockCnsmpnValueInCC",
 "PrevMonthStockCnsmpnValueInGC","PreviousCalendarMonth","PreviousCalendarMonthX2","PreviousYearEndMonth",
 "StockCnsmpnValue3MAInCC","StockCnsmpnValue3MAInGC","StockCnsmpnValueInCC","StockCnsmpnValueInGC",
 "TurnoverCnsmpnQty3MA","TurnoverCnsmpnValue3MAInCC","TurnoverCnsmpnValue3MAInGC"}

def main():
    d = json.load(open(SRC))
    full = copy.deepcopy(d)
    um = json.loads(full["editorSettings"][SRC_VIEW]["uiModel"])
    c = um["contents"]
    owner, nodes, elems = U.build_index(c)
    name2u = {(n.get('name') or n.get('alias')): u for u,n in nodes.items()}
    P14 = name2u["Projection 14"]

    succ={}; pred={}
    for u,n in nodes.items():
        s=n.get("successorNode"); t=[s] if isinstance(s,str) and s else (s or [])
        succ[u]=t
        for x in t: pred.setdefault(x,[]).append(u)

    # ancestros de P14 = subgrafo base a podar
    base=set(); st=list(pred.get(P14,[]))
    while st:
        u=st.pop()
        if u in base: continue
        base.add(u); st+=pred.get(u,[])

    # ---- recolectar UUIDs de elementos de los nodos base (para limpiar refs) ----
    base_elem_uuids=set()
    for u in base:
        base_elem_uuids |= set(nodes[u].get("elements",{}).keys())

    # plantilla de elemento-de-entidad (clonar de una entidad existente del enriquecimiento)
    ent_tmpl_uuid = name2u["2SR_MATDOCGM_01"]
    sample_eid = next(iter(nodes[ent_tmpl_uuid]["elements"]))
    elem_tmpl = {k:v for k,v in c[sample_eid].items() if k in ("classDefinition",)}

    # ---- 1) crear Entity nuevo + sus elementos, enlazado a P14 ----
    import uuid as _uuid
    def nid(): return str(_uuid.uuid4())
    new_ent = nid()
    # columnas que P14 consume y SI estan en el original = P14 elems cuyo expression no esta en DROP
    p14_keep = []  # (entity_col, p14_elem_uuid)
    for euid in list(nodes[P14]["elements"].keys()):
        el=c[euid]
        outn = el.get("newName")
        if outn in DROP:
            # quitar este elemento de P14 (columna que el original no tiene)
            del nodes[P14]["elements"][euid]
            c.pop(euid, None)
            continue
        # nombre real de la columna = newName. Normalizar P14 a pass-through del Entity:
        col = outn
        el["name"]=col
        el["expression"]=col
        el["isCalculated"]=False
        nodes[P14]["elements"][euid]={"name":col}
        p14_keep.append((col, euid))

    ent_elements={}   # light refs para el Entity
    for col, p14e in p14_keep:
        eid=nid()
        c[eid]={"classDefinition":"sap.cdw.querybuilder.Element","name":col,"newName":col,
                "expression":None,"successorElement":p14e}
        ent_elements[eid]={"name":col}
    # nodo Entity
    c[new_ent]={
        "classDefinition":"sap.cdw.querybuilder.Entity","name":BASE_REF,"label":"Inventory Balance (original)",
        "type":3,"isDeltaOutboundOn":False,"isPinToMemoryEnabled":False,"isHiddenInUi":False,
        "#objectStatus":1,"elements":ent_elements,"successorNode":P14}

    # ---- 2) PODAR subgrafo base ----
    # quitar nodos base + sus elementos
    for u in base:
        for euid in list(nodes[u].get("elements",{}).keys()):
            c.pop(euid, None)
        c.pop(u, None)
    # quitar simbolos cuyo 'object' apunta a un nodo base
    for sid in [s for s,n in list(c.items()) if isinstance(n,dict) and n.get("object") in base]:
        c.pop(sid, None)
    # quitar ElementMappings y AssociationSymbols que referencian elementos/nodos eliminados
    gone = lambda x: (x is not None) and (x not in c)
    for sid,n in list(c.items()):
        if not isinstance(n,dict): continue
        cd=n.get("classDefinition","")
        if cd=="sap.cdw.commonmodel.ElementMapping":
            if gone(n.get("source")) or gone(n.get("target")): c.pop(sid,None)
        elif cd=="sap.cdw.querybuilder.ui.AssociationSymbol":
            if gone(n.get("object")) or gone(n.get("source")) or gone(n.get("target")): c.pop(sid,None)

    # ---- 3) DROP de las 14 columnas en TODOS los nodos downstream restantes ----
    for u,n in list(c.items()):
        if not isinstance(n,dict): continue
        if "elements" in n and isinstance(n["elements"],dict):
            for euid in list(n["elements"].keys()):
                fe=c.get(euid,{})
                if isinstance(fe,dict) and fe.get("newName") in DROP:
                    del n["elements"][euid]
                    c.pop(euid,None)
    # limpiar successorElement colgantes (a elementos ya removidos)
    for u,n in list(c.items()):
        if isinstance(n,dict) and "successorElement" in n and n["successorElement"] not in c:
            n["successorElement"]=None

    # ---- 4) limpiar Diagram.symbols + añadir símbolo del Entity nuevo ----
    diag=[n for n in c.values() if isinstance(n,dict) and n.get("classDefinition")=="sap.cdw.querybuilder.ui.Diagram"][0]
    for sid in list(diag.get("symbols",{}).keys()):
        if sid not in c: del diag["symbols"][sid]
    ent_sym=nid()
    c[ent_sym]={"classDefinition":"sap.cdw.querybuilder.ui.EntitySymbol","name":"EntitySymbol_INV",
                "x":-2000,"y":-60,"width":200,"displayName":BASE_REF,"object":new_ent}
    diag.setdefault("symbols",{})[ent_sym]={"name":"EntitySymbol_INV"}

    # ---- 5) Model: nodes (quitar base, añadir entity), name/label ----
    model=[n for n in c.values() if isinstance(n,dict) and n.get("classDefinition")=="sap.cdw.querybuilder.Model"][0]
    for u in base: model.get("nodes",{}).pop(u,None)
    model.setdefault("nodes",{})[new_ent]={"name":BASE_REF}
    model["name"]=NEW_VIEW; model["label"]=NEW_VIEW

    # ---- 6) Output node: nombre + quitar cols dropeadas (ya hecho en paso 3) ----
    out=[n for n in c.values() if isinstance(n,dict) and n.get("classDefinition")=="sap.cdw.querybuilder.Output"][0]
    out["name"]=NEW_VIEW

    # ================= QUERY CSN =================
    qdef = full["definitions"][SRC_VIEW]
    q = qdef["query"]
    # localizar el join spine⟕base y reemplazar arg1 (base SELECT) por ref al 2VR original
    def find_and_graft(node):
        if isinstance(node,dict):
            if node.get("join") and "args" in node and len(node["args"])==2:
                a0,a1=node["args"]
                def is_base(a): return isinstance(a,dict) and "SELECT" in a and '"2VR_SCM_MATDOC_03"' in json.dumps(a)
                def is_spine(a): return isinstance(a,dict) and '"2SR_MATDOCGM_01"' in json.dumps(a)
                if is_spine(a0) and is_base(a1):
                    node["args"][1]={"ref":[BASE_REF],"as":"Aggregation 2"}
                    return True
            for v in node.values():
                if find_and_graft(v): return True
        elif isinstance(node,list):
            for v in node:
                if find_and_graft(v): return True
        return False
    grafted = find_and_graft(q)
    # quitar columnas dropeadas de TODAS las listas 'columns' del CSN
    def col_dropped(col):
        if not isinstance(col,dict): return False
        if col.get("as") in DROP: return True
        # columnas de proyección raíz: ref sin 'as' -> alias implícito = ref[-1]
        if col.get("as") is None and isinstance(col.get("ref"),list) and col["ref"] and col["ref"][-1] in DROP:
            return True
        return False
    def strip_cols(node):
        if isinstance(node,dict):
            if "columns" in node and isinstance(node["columns"],list):
                node["columns"]=[col for col in node["columns"] if not col_dropped(col)]
            for v in node.values(): strip_cols(v)
        elif isinstance(node,list):
            for v in node: strip_cols(v)
    strip_cols(q)

    # ================= definitions =================
    defs=full["definitions"]
    newdef=copy.deepcopy(qdef)
    # elements de salida = quitar las dropeadas
    newdef["elements"]={k:v for k,v in qdef["elements"].items() if k not in DROP}
    newdef["@EndUserText.label"]="Inventory Balance for Obsolete Material"
    defs[NEW_VIEW]=newdef
    del defs[SRC_VIEW]
    # asegurar que el 2VR original exista como fuente (stub con sus elementos = los 61 que consumimos)
    # reusar la def vieja (la enriquecida) como stub de la fuente NO sirve; creamos stub minimo:
    if BASE_REF not in defs:
        cols=[col for col,_ in p14_keep]
        base_types=qdef.get("elements",{})   # tipos reales (la def vieja del 2VR los tiene)
        defs[BASE_REF]={"kind":"entity",
                        "elements":{col: base_types.get(col,{"type":"cds.String"}) for col in cols},
                        "@EndUserText.label":"Inventory Balance"}
    # quitar fuentes base huérfanas (timedim, matdoc_03, ckmlhd) si ya no se referencian
    blob=json.dumps({k:v for k,v in defs.items() if k!=NEW_VIEW})
    qblob=json.dumps(newdef.get("query"))
    for orphan in ["2VR_SCM_MATDOC_03","2VR_MD_TIMEDIMENSIONS_01","2VR_SCM_CKMLHD_02"]:
        if orphan in defs and f'"{orphan}"' not in qblob:
            del defs[orphan]

    # ================= editorSettings =================
    es=full["editorSettings"]
    es[NEW_VIEW]=es.pop(SRC_VIEW)
    es[NEW_VIEW]["uiModel"]=json.dumps(um, ensure_ascii=False)

    import os; os.makedirs("output",exist_ok=True)
    json.dump(full, open(OUT_JSON,"w"), ensure_ascii=False, indent=1)
    print("grafted CSN:", grafted)
    print("Entity nuevo:", new_ent[:8], "| cols expuestas:", len(p14_keep))
    print("nodos base podados:", len(base))
    print("salida (elements):", len(newdef["elements"]))
    print("escrito:", OUT_JSON, os.path.getsize(OUT_JSON), "bytes")

if __name__=="__main__":
    main()
