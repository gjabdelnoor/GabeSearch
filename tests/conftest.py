import sys
import types
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Stub external dependencies to avoid import errors during testing

# Helper to create simple module with attributes
def stub_module(name, attrs):
    module = types.ModuleType(name)
    for attr_name, attr_value in attrs.items():
        setattr(module, attr_name, attr_value)
    sys.modules[name] = module
    return module

# qdrant_client stubs
if 'qdrant_client' not in sys.modules:
    stub_module('qdrant_client', {'QdrantClient': object})
    qm = types.SimpleNamespace(
        VectorParams=object,
        Distance=types.SimpleNamespace(COSINE=object),
        OptimizersConfigDiff=object,
    )
    stub_module('qdrant_client.http', {'models': qm})
    sys.modules['qdrant_client.http.models'] = qm

# FlagEmbedding stub
if 'FlagEmbedding' not in sys.modules:
    stub_module('FlagEmbedding', {'BGEM3FlagModel': object})

# bs4 stub
if 'bs4' not in sys.modules:
    stub_module('bs4', {'BeautifulSoup': object})

# mcp stubs
if 'mcp' not in sys.modules:
    class DummyServer:
        def __init__(self, *a, **k):
            pass
        def call_tool(self):
            def decorator(f):
                return f
            return decorator
        def list_tools(self):
            def decorator(f):
                return f
            return decorator
        def run(self, *a, **k):
            pass
    async def _async_ctx():
        class _Ctx:
            async def __aenter__(self):
                return None, None
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return _Ctx()
    server_mod = stub_module('mcp.server', {'Server': DummyServer})
    transport_stdio_mod = stub_module('mcp.transport.stdio', {'stdio_transport': lambda: _async_ctx()})
    transport_mod = stub_module('mcp.transport', {'stdio': transport_stdio_mod})
    types_mod = stub_module('mcp.types', {'Tool': object, 'TextContent': object})
    mcp_mod = stub_module('mcp', {'server': server_mod, 'transport': transport_mod, 'types': types_mod})

# aiohttp and httpx stubs if missing
if 'aiohttp' not in sys.modules:
    stub_module('aiohttp', {'ClientSession': object, 'ClientError': Exception})
if 'httpx' not in sys.modules:
    stub_module('httpx', {'AsyncClient': object})
