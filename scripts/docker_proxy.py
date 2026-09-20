#!/opt/venv/bin/python
"""Private Docker CLI adapter used only in tools images."""
import sys
sys.path.insert(0, '/opt/tool-code')
from deploy.docker_bridge import main

try:
    raise SystemExit(main(sys.argv[1:]))
except ValueError as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(2)
