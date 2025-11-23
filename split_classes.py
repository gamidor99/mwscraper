import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

CHRONICLES = ["eternal", "lu4", "live"]
DEFAULT_CHRONICLE = "eternal"


def get_chronicle():
    if len(sys.argv) > 1:
        c = sys.argv[1].lower().strip()
        if c in CHRONICLES:
            return c
        print(f"⚠️ Unknown chronicle '{c}', using {DEFAULT_CHRONICLE}")
    return DEFAULT_CHRONICLE


def save_clean_pretty_xml(elem, path):
    rough = ET.tostring(elem, encoding="utf-8")

    # Parse with minidom
    reparsed = minidom.parseString(rough)

    # top-prettyxml but removing blank lines
    pretty_bytes = reparsed.toprettyxml(indent="  ", encoding="utf-8")
    pretty_str = pretty_bytes.decode("utf-8")

    # Remove empty whitespace-only lines
    cleaned = "\n".join([line for line in pretty_str.split("\n") if line.strip() != ""])

    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned)



def find_parent_class(root, class_elem):
    """Locate the parent <class> of a given class."""
    for elem in root.findall(".//class"):
        for child in elem.findall("class"):
            if child is class_elem:
                return elem
    return None


def find_child_class(class_elem):
    """Return first nested <class> child (if any)."""
    child = class_elem.find("class")
    return child


def get_race_and_subtype2(root, cls):
    race = None
    subtype = None

    exit(0)

def get_race_and_subtype(root, cls):
    race = None
    subtype = None

    # build a parent map: child_element -> parent_element
    parent_map = {child: parent for parent in root.iter() for child in parent}

    # start from the immediate parent of this class element
    p = parent_map.get(cls)

    # climb upward to find <subtype> and <race>
    while p is not None:
        if p.tag == "subtype":
            subtype = p.get("name")
        elif p.tag == "race":
            race = p.get("name")
        p = parent_map.get(p)

    return race, subtype

def get_child_class_name(class_elem):
    child = class_elem.find("class")
    if child is not None:
        return child.get("name")
    return "none"


def get_parent_class_name(class_elem, parent_map):
    p = parent_map.get(class_elem)
    if p is not None and p.tag == "class":
        return p.get("name")
    return "none"


def main():
    chronicle = get_chronicle()
    input_file = f"data/races_classes/races_classes_skills_{chronicle}.xml"
    output_dir = f"data/races_classes/splited/{chronicle}/"

    if not os.path.exists(input_file):
        print(f"❌ Missing input: {input_file}")
        return

    print(f"📘 Reading: {input_file}")
    os.makedirs(output_dir, exist_ok=True)

    tree = ET.parse(input_file)
    root = tree.getroot()

    all_classes = root.findall(".//class")
    total = 0



    for cls in all_classes:
        class_name = cls.get("name")

        

        # --- Metadata ---
        race, subtype = get_race_and_subtype(root, cls)

        parent_elem = find_parent_class(root, cls)
        child_elem = find_child_class(cls)

        print(f"Processing class: {class_name} (race={race}, subtype={subtype}, parent={parent_elem.get('name') if parent_elem is not None else 'none'}, child={child_elem.get('name') if child_elem is not None else 'none'})" )

        child_of = parent_elem.get("name") if parent_elem is not None else "none"
        parent_of = child_elem.get("name") if child_elem is not None else "none"

        # --- Create flat output ---
        out_root = ET.Element(
            "class",
            {
                "race": race or "",
                "subtype": subtype or "",
                "name": class_name,
                "child_of": child_of,
                "parent_of": parent_of,
            }
        )

        # copy skills_summary
        skills_summary = cls.find("skills_summary")
        if skills_summary is not None:
            out_root.append(skills_summary)

        # copy skills
        skills = cls.find("skills")
        if skills is not None:
            out_root.append(skills)

        # save
        out_path = os.path.join(output_dir, f"{class_name.replace(' ', '_')}.xml")
        save_clean_pretty_xml(out_root, out_path)

        print(f"✔ Saved {out_path}")
        total += 1

    print(f"\n🎉 Done! Exported {total} classes → {output_dir}")


if __name__ == "__main__":
    main()
