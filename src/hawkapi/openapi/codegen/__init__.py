"""HawkAPI OpenAPI client code generator — public API."""

from hawkapi.openapi.codegen.ir import ClientIR
from hawkapi.openapi.codegen.parser import build_client_ir
from hawkapi.openapi.codegen.python import generate_python_client
from hawkapi.openapi.codegen.typescript import generate_typescript_client

__all__ = [
    "ClientIR",
    "build_client_ir",
    "generate_python_client",
    "generate_typescript_client",
]
