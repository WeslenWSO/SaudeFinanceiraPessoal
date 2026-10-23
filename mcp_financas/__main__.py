"""python -m mcp_financas [--transport stdio|sse|streamable-http]"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description='MCP Saúde Financeira')
    parser.add_argument(
        '--transport',
        default=os.environ.get('MCP_TRANSPORT', 'stdio'),
        choices=('stdio', 'sse', 'streamable-http'),
    )
    args = parser.parse_args()
    from mcp_financas.server import run

    run(transport=args.transport)


if __name__ == '__main__':
    main()
