import re
with open("tests/test_graph_routing.py", "r") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if 'agents.script("milestone_reviewer"' in line:
        # duplicate line and change milestone_reviewer to security_reviewer
        # and _milestone_review to _security_review
        sec_line = line.replace('milestone_reviewer', 'security_reviewer').replace('_milestone_review', '_security_review')
        # Insert security review BEFORE milestone review in the tests (since it runs before)
        # Wait, the script just queues them, order in `agents.script` calls doesn't actually matter because they are keyed by role name!
        new_lines.append(sec_line)

with open("tests/test_graph_routing.py", "w") as f:
    f.writelines(new_lines)
