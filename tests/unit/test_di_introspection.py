from hawkapi.di.container import Container
from hawkapi.di.introspection import container_graph, to_mermaid


class Service:
    pass


class Repository:
    pass


class TestDIIntrospection:
    def test_graph_returns_providers(self):
        c = Container()
        c.singleton(Service, factory=Service)
        graph = container_graph(c)
        assert "Service" in graph

    def test_graph_shows_lifecycle(self):
        c = Container()
        c.scoped(Repository, factory=Repository)
        graph = container_graph(c)
        assert graph["Repository"]["lifecycle"] == "scoped"

    def test_empty_container(self):
        c = Container()
        graph = container_graph(c)
        assert graph == {}

    def test_to_mermaid(self):
        c = Container()
        c.singleton(Service, factory=Service)
        c.scoped(Repository, factory=Repository)
        mermaid = to_mermaid(c)
        assert "graph TD" in mermaid
        assert "Service" in mermaid
