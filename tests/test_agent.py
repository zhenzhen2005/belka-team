def test_agent_module_loads_without_errors():
    import agent

    assert agent.agent is not None
