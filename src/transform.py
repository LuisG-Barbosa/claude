#!/usr/bin/env python3
"""
Transforma HA_GV_EAM_TR_MATDOCBYGOODSRECEIPT_01 (OLD, estructura correcta) en
2VR_TR_MATDOCBYGOODSRECEIPT_01 (nueva arquitectura).

Estrategia (mínima superficie de cambio, máxima consistencia):
  - Contenedor = _02 (definitions/query CSN ya correctos + meta importable).
  - Se REEMPLAZA SOLO editorSettings[view].uiModel por el uiModel del OLD
    transformado en el borde de lectura (leaf), dejando TODO lo interno
    byte-idéntico al original que sí funciona.

Regla del borde (leaf):
  Para cada columna de cada Entity, se camina el linaje (successorElement):
    * Entity (+Filter previo): name=newName=NOMBRE_FUENTE_NUEVO.
    * Primera RenameElements (bridge): name=NOMBRE_FUENTE_NUEVO; newName se
      CONSERVA (alias interno) si el elemento continúa aguas abajo
      (successorElement presente), si no, se pone el nombre nuevo.
    * Aguas abajo del bridge: SIN TOCAR (alias internos preservados).
  Condiciones de Filter cuyo predecesor es una Entity (Filter 1-6): se
  remapean columnas de fuente vieja->nueva por límite de palabra.
"""
import json, re, copy, sys
sys.path.insert(0, "src")
import uimodel as U

OLD_PATH = "input/HA_OLD.json"
NEW_PATH = "input/2VR_NEW.json"
OLD_VIEW = "HA_GV_EAM_TR_MATDOCBYGOODSRECEIPT_01"
NEW_VIEW = "2VR_TR_MATDOCBYGOODSRECEIPT_01"
OUT_PATH = "output/2VR_TR_MATDOCBYGOODSRECEIPT_01.FIXED.json"

RENAME = "sap.cdw.querybuilder.RenameElements"

# ---- mapeos de columnas de fuente (vieja -> nueva) -------------------------
EXPLICIT = {
    "MATDOC": {"Product": "MATERIAL"},   # único rename semántico (no de caja)
    "MARC":   {},                         # Product->PRODUCT, Plant->PLANT son case-only
}

def build_colmap(old_cols, new_set, explicit):
    ci = {c.upper(): c for c in new_set}
    m = {}
    for c in old_cols:
        if c in explicit:        m[c] = explicit[c]
        elif c in new_set:       m[c] = c            # exacta
        elif c.upper() in ci:    m[c] = ci[c.upper()]  # solo caja
        else:                    m[c] = c            # sin equivalente: se deja
    return m

def main():
    dO, umO, cO = U.load(OLD_PATH, OLD_VIEW)
    dN, umN, cN = U.load(NEW_PATH, NEW_VIEW)
    ownerO, nodesO, elemsO = U.build_index(cO)

    new_matdoc = set(dN["definitions"]["2VR_SCM_MATDOC_02"]["elements"].keys())
    new_marc   = set(dN["definitions"]["2VR_MD_MARC_01"]["elements"].keys())

    contents = umO["contents"]   # editaremos esta copia (de OLD)

    # successorNode graph (para condiciones de filtro: ¿predecesor=Entity?)
    pred = {}
    for uid, n in nodesO.items():
        s = n.get("successorNode"); t = [s] if isinstance(s, str) and s else (s or [])
        for x in t:
            pred.setdefault(x, []).append(uid)

    def first_bridge(start):
        cur = start; seen = set(); prelist = []
        while cur and cur in elemsO and cur not in seen:
            seen.add(cur); ow = ownerO.get(cur)
            if ow and ow[1] == RENAME:
                return prelist, cur
            prelist.append(cur)
            cur = elemsO[cur].get("successorElement")
        return prelist, None

    def set_name(euid, owner_uuid, newname, also_newname=True):
        """Actualiza el Element completo y la ref ligera del nodo dueño."""
        el = contents.get(euid)
        if isinstance(el, dict):
            el["name"] = newname
            if also_newname:
                el["newName"] = newname
        ln = contents[owner_uuid]["elements"].get(euid)
        if isinstance(ln, dict):
            ln["name"] = newname

    stats = {"entities": 0, "cols_renamed": 0, "bridges": 0, "filters": 0}
    log = []

    # ---- 1) Entidades: metadata + columnas + bridge ------------------------
    for ent_uuid, ent in list(nodesO.items()):
        if ent.get("classDefinition") != "sap.cdw.querybuilder.Entity":
            continue
        stats["entities"] += 1
        old_name = ent.get("name")
        is_marc = old_name == "CBA_MD.DI_ProductPlant"
        new_set = new_marc if is_marc else new_matdoc
        explicit = EXPLICIT["MARC"] if is_marc else EXPLICIT["MATDOC"]

        # metadata de entidad: copiar EXACTO lo que el _02 puso (mismo UUID)
        src02 = cN.get(ent_uuid, {})
        for fld in ("name", "label", "alias"):
            if fld in src02:
                contents[ent_uuid][fld] = src02[fld]

        # mapa de columnas para esta fuente
        old_cols = [elemsO[e]["name"] for e in ent["elements"]]
        colmap = build_colmap(old_cols, new_set, explicit)

        for euid in list(ent["elements"].keys()):
            oldc = elemsO[euid]["name"]
            newc = colmap[oldc]
            prelist, bridge = first_bridge(euid)
            # pre-bridge: entity + (filter) -> nombre de fuente nuevo (name+newName)
            for puid in prelist:
                set_name(puid, ownerO[puid][0], newc, also_newname=True)
            # bridge: name=nuevo; newName conserva alias interno si continúa
            if bridge is not None:
                stats["bridges"] += 1
                cont = bool(elemsO[bridge].get("successorElement"))
                bridge_owner = ownerO[bridge][0]
                set_name(bridge, bridge_owner, newc, also_newname=False)
                if not cont:
                    # columna descartada aquí: newName=nuevo (consistencia local)
                    contents[bridge]["newName"] = newc
                    contents[bridge_owner]["elements"][bridge]["name"] = newc
                else:
                    # viva: solo aseguramos que la ref ligera muestre el name de entrada nuevo
                    contents[bridge_owner]["elements"][bridge]["name"] = newc
            if newc != oldc:
                stats["cols_renamed"] += 1
                if oldc in ("Product", "Plant", "PostingDate", "GoodsMovementType"):
                    log.append(f"   {ent.get('alias'):26s} {oldc} -> {newc} (bridge cont={bool(bridge and elemsO[bridge].get('successorElement'))})")

    # ---- 2) Condiciones de Filter cuyo predecesor es Entity ----------------
    # mapa global vieja->nueva para condiciones (solo las 4 clave + caja)
    cond_map_matdoc = build_colmap(
        ["GoodsMovementType", "Product", "Plant", "PostingDate", "PostingMonth"],
        new_matdoc, EXPLICIT["MATDOC"])
    def remap_condition(text, cmap):
        out = text
        # de más largo a más corto para evitar solapamientos parciales
        for old in sorted(cmap, key=len, reverse=True):
            new = cmap[old]
            if old == new:
                continue
            out = re.sub(r'(?<![A-Za-z0-9_])' + re.escape(old) + r'(?![A-Za-z0-9_])', new, out)
        return out

    for fuid, fn in list(nodesO.items()):
        if fn.get("classDefinition") != "sap.cdw.querybuilder.Filter":
            continue
        preds = pred.get(fuid, [])
        pred_is_entity = any(
            nodesO.get(p, {}).get("classDefinition") == "sap.cdw.querybuilder.Entity"
            for p in preds)
        if pred_is_entity and contents[fuid].get("condition"):
            new_cond = remap_condition(contents[fuid]["condition"], cond_map_matdoc)
            if new_cond != contents[fuid]["condition"]:
                contents[fuid]["condition"] = new_cond
                stats["filters"] += 1

    # ---- 3) Quitar contexto CBA_MD + actualizar Model ----------------------
    # localizar nodos Context y Model
    to_delete = []
    for uid, n in list(contents.items()):
        if isinstance(n, dict) and n.get("classDefinition") == "sap.cdw.commonmodel.Context":
            to_delete.append(uid)
    for uid in to_delete:
        del contents[uid]

    for uid, n in contents.items():
        if isinstance(n, dict) and n.get("classDefinition") == "sap.cdw.querybuilder.Model":
            n["name"] = NEW_VIEW
            n["label"] = NEW_VIEW
            # contexts: quitar CBA_MD
            ctx = n.get("contexts", {})
            if isinstance(ctx, dict):
                n["contexts"] = {k: v for k, v in ctx.items() if v.get("name") != "CBA_MD"}
            # nodes: refrescar el name de cada entity al de _02
            nd = n.get("nodes", {})
            for nid, meta in nd.items():
                if nid in cN and cN[nid].get("classDefinition") == "sap.cdw.querybuilder.Entity":
                    meta["name"] = cN[nid].get("name", meta.get("name"))

    # ---- 4) Ensamblar: contenedor = _02, reemplazar SOLO el uiModel --------
    result = copy.deepcopy(dN)
    # etiqueta cosmética de la entidad principal (heredada del _02 con nombre viejo)
    if result["definitions"][NEW_VIEW].get("@EndUserText.label", "").startswith("HA_"):
        result["definitions"][NEW_VIEW]["@EndUserText.label"] = NEW_VIEW
    result["editorSettings"][NEW_VIEW]["uiModel"] = json.dumps(umO, ensure_ascii=False)

    import os
    os.makedirs("output", exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    print("=== Transformación completada ===")
    print(json.dumps(stats, indent=2))
    print("\nRenames clave (muestra):")
    print("\n".join(log[:20]))
    print(f"\nEscrito: {OUT_PATH}")

if __name__ == "__main__":
    main()
