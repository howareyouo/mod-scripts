
def insert_lines(file_path: str, search_term: str, text_lines: list[str]) -> None:
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    # 查找包含搜索词的行
    for i, line in enumerate(lines):
        if search_term in line:
            lines[i:i] = [l + '\n' for l in text_lines]
            break
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(lines)

insert_text = [
    '\t# Blender hide bones:',
    '\tarmatureObj.hide_viewport = True',
    '\tarmatureObj.hide_render = True',
]

insert_lines(
    r"F:\Program Files\Blender\portable\scripts\addons\RE-Mesh-Editor-main\modules\mesh\blender_re_mesh.py",
    'print(f"Mesh imported in', 
    insert_text
)
