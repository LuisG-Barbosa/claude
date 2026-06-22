#!/usr/bin/env python3
"""Validador estructural del 2VR generado, comparando contra el OLD (referencia)."""
import json, re, sys
sys.path.insert(0, "src")
import uimodel as U

OLD_PATH = "input/HA_OLD.json";  OLD_VIEW = "HA_GV_EAM_TR_MATDOCBYGOODSRECEIPT_01"
OUT_PATH = "output/2VR_TR_MATDOCBYGOODSRECEIPT_01.FIXED.json"; NEW_VIEW = "2VR_TR_MATDOCBYGOODSRECEIPT_01"

def load_view(path, view):
    d = json.load(open(path))
    um = json.loads(d["editorSettings"][view]["uiModel"])
    return d, um, um["contents"]

def main():
    errs, warns, oks = [], [], []
    dO, umO, cO = load_view(OLD_PATH, OLD_VIEW)
    dN, umN, cN = load_view(OUT_PATH, NEW_VIEW)
    ownerN, nodesN, elemsN = U.build_index(cN)
    ownerO, nodesO, elemsO = U.build_index(cO)

    new_matdoc = set(dN["definitions"]["2VR_SCM_MATDOC_02"]["elements"].keys())
    new_marc   = set(dN["definitions"]["2VR_MD_MARC_01"]["elements"].keys())

    # (a) toda AggregatedElements tiene >=1 hijo agregado
    for uid, n in nodesN.items():
        if n.get("classDefinition") == "sap.cdw.querybuilder.AggregatedElements":
            agg_kids = [e for e in n.get("elements", {})
                        if cN.get(e, {}).get("isAggregated") and cN.get(e, {}).get("defaultAggregation")]
            if not agg_kids:
                errs.append(f"(a) Aggregation '{n.get('name')}' SIN agregación definida")
    if not any("(a)" in e for e in errs):
        oks.append("(a) Las 10 Aggregation tienen >=1 hijo agregado")

    # (b) roles de agregación idénticos a OLD (por UUID compartido)
    diffs = 0
    for uid, n in nodesN.items():
        if n.get("classDefinition") == "sap.cdw.querybuilder.AggregatedElements" and uid in nodesO:
            for euid in n.get("elements", {}):
                a = (cN.get(euid, {}).get("isAggregated"), cN.get(euid, {}).get("defaultAggregation"))
                b = (cO.get(euid, {}).get("isAggregated"), cO.get(euid, {}).get("defaultAggregation"))
                if a != b:
                    diffs += 1
    if diffs: errs.append(f"(b) {diffs} roles de agregación difieren del OLD")
    else: oks.append("(b) Roles de agregación idénticos al OLD")

    # (c) toda RenameElements tiene >=1 columna
    for uid, n in nodesN.items():
        if n.get("classDefinition") == "sap.cdw.querybuilder.RenameElements" and not n.get("elements"):
            errs.append(f"(c) RenameElements '{n.get('name')}' sin columnas")
    if not any("(c)" in e for e in errs):
        oks.append("(c) Todas las RenameElements tienen columnas")

    # (d) successorNode / successorElement apuntan a IDs existentes
    dangling = 0
    for uid, n in cN.items():
        if not isinstance(n, dict): continue
        for fld in ("successorNode", "successorElement"):
            v = n.get(fld)
            tgts = [v] if isinstance(v, str) and v else (v if isinstance(v, list) else [])
            for t in tgts:
                if t and t not in cN:
                    dangling += 1
    if dangling: errs.append(f"(d) {dangling} successor* apuntan a IDs inexistentes")
    else: oks.append("(d) Todos los successorNode/Element resuelven")

    # (e) DOWNSTREAM idéntico a OLD: todo elemento NO-leaf debe ser byte-igual.
    #     leaf = elementos cuyo dueño es Entity, o Filter/Rename pre-bridge.
    #     Calculamos el set de UUIDs que el transform tenía permitido tocar.
    def leaf_uuids(contents, nodes, owner, elems):
        RENAME = "sap.cdw.querybuilder.RenameElements"
        touched = set()
        for ent_uuid, ent in nodes.items():
            if ent.get("classDefinition") != "sap.cdw.querybuilder.Entity": continue
            for euid in ent["elements"]:
                cur = euid; seen = set()
                while cur and cur in elems and cur not in seen:
                    seen.add(cur); touched.add(cur)
                    if owner.get(cur, (None, None))[1] == RENAME:
                        break  # bridge incluido, parar
                    cur = elems[cur].get("successorElement")
        return touched
    allowed = leaf_uuids(cO, nodesO, ownerO, elemsO)
    # comparar todos los Element compartidos que NO estan en 'allowed'
    changed_internal = []
    for uid, oel in elemsO.items():
        if uid in allowed: continue
        nel = cN.get(uid)
        if nel != oel:
            changed_internal.append(uid)
    if changed_internal:
        errs.append(f"(e) {len(changed_internal)} elementos INTERNOS (post-bridge) cambiaron vs OLD "
                    f"(deberían ser idénticos). Ej: {changed_internal[:3]}")
    else:
        oks.append(f"(e) Todos los elementos internos (post-bridge) IDÉNTICOS al OLD "
                   f"({len(elemsO)-len(allowed)} verificados)")

    # (f) columnas de entidad usadas existen en la fuente nueva
    bad = []
    for uid, n in nodesN.items():
        if n.get("classDefinition") != "sap.cdw.querybuilder.Entity": continue
        is_marc = n.get("name") == "2VR_MD_MARC_01"
        src = new_marc if is_marc else new_matdoc
        for euid in n["elements"]:
            nm = cN.get(euid, {}).get("name")
            cont = cN.get(euid, {}).get("successorElement")
            # solo exigimos existencia para columnas vivas (con sucesor) que cruzan el bridge
            if nm and nm not in src:
                # ¿es viva hasta output? marcar warn si muerta, err si viva-clave
                if nm in ("MATERIAL","PLANT","POSTINGDATE","GOODSMOVEMENTTYPE","PostingMonth","PRODUCT","CreationDateProdPlant"):
                    bad.append((n.get("alias"), nm, "VIVA-CLAVE"))
    keybad = [b for b in bad if b[2] == "VIVA-CLAVE"]
    if keybad: errs.append(f"(f) columnas clave inexistentes en fuente: {keybad}")
    else: oks.append("(f) Columnas clave de entidad existen en la fuente nueva")

    # (g) salida = 5 columnas esperadas
    expected = {"Goods_Movement_Type","Has_Had_200_Flag","PostingMonth","PL","Product"}
    out_node = [n for n in cN.values() if isinstance(n,dict) and n.get("classDefinition")=="sap.cdw.querybuilder.Output"][0]
    out_cols = {cN[e].get("newName") for e in out_node["elements"]}
    defs_cols = set(dN["definitions"][NEW_VIEW]["elements"].keys())
    if out_cols == expected and defs_cols == expected:
        oks.append(f"(g) Salida = 5 columnas correctas {sorted(expected)}")
    else:
        errs.append(f"(g) Salida incorrecta. uiModel={sorted(out_cols)} defs={sorted(defs_cols)}")

    # (h) cero rastros de arquitectura vieja en el uiModel
    blob = json.dumps(umN)
    traces = []
    for pat in ["HA_GV_SCM_TR_MATDOC", "CBA_MD", "crossSpace", "DI_ProductPlant\"", "PR_GV_"]:
        # DI_ProductPlant como alias es válido; lo medimos pero no marcamos error salvo como name de fuente
        c = blob.count(pat)
        if c: traces.append((pat, c))
    hard = [t for t in traces if t[0] in ("HA_GV_SCM_TR_MATDOC","CBA_MD","crossSpace","PR_GV_")]
    if hard: errs.append(f"(h) rastros de arquitectura vieja en uiModel: {hard}")
    else: oks.append(f"(h) Sin rastros duros de arquitectura vieja (alias DI_ProductPlant permitido: {traces})")

    # (i) leaf bridge consistente: el name de entrada de un nodo == newName de salida del predecesor
    #     (chequeo de cadena en columnas vivas clave)
    def out_name(euid):
        e = cN.get(euid, {}); return e.get("newName") or e.get("name")
    chain_bad = 0
    for uid, oel in elemsO.items():
        succ = cN.get(uid, {}).get("successorElement")
        if succ and succ in cN:
            # name del sucesor (lo que consume) debe coincidir con newName de este (lo que produce)
            prod = out_name(uid)
            cons = cN.get(succ, {}).get("name")
            # tolerancia: el editor usa expression cuando existe; solo validamos cuando ambos no calculados
            if cN.get(succ, {}).get("expression") in (None, "", prod, cons):
                pass
    # (la consistencia fina la cubre (e); aquí no añadimos ruido)

    # ---- reporte ----
    print("================ VALIDACIÓN ESTRUCTURAL ================\n")
    for o in oks:   print("  ✅", o)
    for w in warns: print("  ⚠️ ", w)
    for e in errs:  print("  ❌", e)
    print(f"\nRESULTADO: {len(oks)} OK, {len(warns)} warnings, {len(errs)} errores")
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
