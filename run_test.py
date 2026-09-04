from tests.test_graph_routing import _graph, _document, _repository, _intake, _tools, _spec, _rejected_review, _approved_review, ScriptedAgents, _script_through_sprint, start_workflow, responds_with

def run():
    import tempfile
    import pathlib
    with tempfile.TemporaryDirectory() as d:
        agents = ScriptedAgents()
        agents.script("product_manager", [responds_with(_intake())])
        agents.script("tools_models", [responds_with(_tools())])
        agents.script("principal_architect", [responds_with(_spec("first draft")), responds_with(_spec("revised with auth"))])
        agents.script("architecture_review", [responds_with(_rejected_review("No authentication described")), responds_with(_approved_review())])
        _script_through_sprint(agents)
        
        state = start_workflow(_graph(), _document(), _repository(pathlib.Path(d)), "run-reject")
        print("STAGE:", state["stage"])
        if "error" in state:
            print("ERROR:", state["error"])

if __name__ == "__main__":
    run()
