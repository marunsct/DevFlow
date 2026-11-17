"""The workflow graph's nodes, grouped by the part of the run they belong to.

Each node is a module-level function of `(state, config)`, or of
`(state, config, ctx)` when it needs the run's models or checkpointer
(`app.graph.context.GraphContext`); `build_workflow_graph` registers it under the
same node name as before.

The helpers a node calls that live in `app.graph.workflow` are imported from it
inside the node, when the node runs, not when this package is imported: a test
that patches `app.graph.workflow.<name>` reaches the node as it did when the
node was a closure inside the builder. The nodes log under the workflow's
logger name for the same reason - what an operator filters on does not move
with the code.
"""
