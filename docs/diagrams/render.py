import plantuml, os, sys
p = plantuml.PlantUML(url='http://www.plantuml.com/plantuml/img/')
diagrams_dir = os.path.dirname(os.path.abspath(__file__))
for f in sorted(os.listdir(diagrams_dir)):
    if not f.endswith('.puml'):
        continue
    path = os.path.join(diagrams_dir, f)
    print(f'Rendering {f}...')
    with open(path, 'r', encoding='utf-8') as fh:
        diagram = fh.read()
    png = p.processes(diagram)
    out = path.replace('.puml', '.png')
    with open(out, 'wb') as fh:
        fh.write(png)
    print(f'  -> {os.path.basename(out)}')
print('Done.')
