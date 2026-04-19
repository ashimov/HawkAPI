"""GraphQL thin-mount subsystem for HawkAPI."""

from __future__ import annotations

from hawkapi.graphql._handler import make_graphql_handler
from hawkapi.graphql._protocol import GraphQLExecutor

__all__ = [
    "GraphQLExecutor",
    "make_graphql_handler",
]
