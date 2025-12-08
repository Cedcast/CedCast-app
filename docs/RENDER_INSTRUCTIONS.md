Rendering instructions
======================

I generated a Graphviz DOT file at `docs/architecture.dot` that describes the system architecture.

To render an SVG or PNG on your machine, install Graphviz and run one of these commands in the repository root:

Render SVG:

```bash
sudo apt update && sudo apt install -y graphviz   # if Graphviz not installed
dot -Tsvg docs/architecture.dot -o docs/architecture.svg
```

Render PNG:

```bash
dot -Tpng docs/architecture.dot -o docs/architecture.png
```

If you prefer not to install system Graphviz, you can use the `graphviz` Python package as a wrapper, but it still requires the `dot` binary. Example (python):

```python
from graphviz import Source
src = Source.from_file('docs/architecture.dot')
src.render(filename='docs/architecture', format='svg', cleanup=False)
```

If you'd like, I can try to install Graphviz on this environment and render the files for you — tell me to proceed and I'll attempt it (may require sudo and could be blocked in some environments). Otherwise, you can render locally and commit the generated SVG/PNG to `docs/` for easy viewing.
