// Core PrimitiveNode is virtual: it writes promoted host widgets, but the
// flattened API prompt can retain the inner writer's old widget value instead.
// Resolve only our writer's three selectors in the serialized queue snapshot.
// Do not change shared subgraph definitions or live widgets: two instances of
// one definition must be able to select different values in the same request.
const FIELDS = ['model', 'writing_mode', 'backend']
const sameId = (a, b) => String(a) === String(b)

function links(graph) {
  return (graph.links ?? []).map((link) => Array.isArray(link)
    ? { id: link[0], origin_id: link[1], origin_slot: link[2], target_id: link[3], target_slot: link[4] }
    : link)
}

function inputLink(context, node, name) {
  const input = node.inputs?.find((slot) => slot.name === name)
  if (input?.link == null) return
  return links(context.graph).find((link) => sameId(link.id, input.link))
}

function enter(context, instance, definition) {
  return { graph: definition, parent: context, instance, path: `${context.path}${instance.id}:` }
}

function primitiveValue(context, link, definitions, visited = new Set()) {
  if (!link) return
  const key = `${context.path}${link.id}`
  if (visited.has(key)) return
  visited.add(key)

  if (context.parent && sameId(link.origin_id, context.graph.inputNode?.id)) {
    // Serialized instances can omit unconnected widget slots. Match the
    // interface name, rather than assuming both slot indices stayed identical.
    const name = context.graph.inputs?.[link.origin_slot]?.name
    if (name == null) return
    return primitiveValue(context.parent,
      inputLink(context.parent, context.instance, name), definitions, visited)
  }

  const source = context.graph.nodes?.find((node) => sameId(node.id, link.origin_id))
  if (!source || source.mode === 4) return
  if (source.type === 'PrimitiveNode') {
    if (source.mode === 2) return
    const value = Array.isArray(source.widgets_values)
      ? source.widgets_values[0]
      : source.widgets_values_named?.value
    return typeof value === 'string' ? { value } : undefined
  }
  if (['Reroute', 'Reroute (rgthree)'].includes(source.type)) {
    const input = source.inputs?.[0]
    const upstream = links(context.graph).find((item) => sameId(item.id, input?.link))
    return primitiveValue(context, upstream, definitions, visited)
  }
  const definition = definitions.get(source.type)
  if (definition && source.mode !== 2) {
    const innerLink = links(definition).find((item) =>
      sameId(item.target_id, definition.outputNode?.id) && item.target_slot === link.origin_slot)
    return primitiveValue(enter(context, source, definition), innerLink, definitions, visited)
  }
  // Real executable sources already have valid API links. Leave them intact.
}

export function repairPrimitiveWriterInputs(workflow, output) {
  if (!workflow?.nodes || !output) return 0
  const definitions = new Map((workflow.definitions?.subgraphs ?? []).map((graph) => [graph.id, graph]))
  let repaired = 0
  for (const [executionId, apiNode] of Object.entries(output)) {
    if (apiNode.class_type !== 'PromptHelperWriter' || !apiNode.inputs) continue
    const path = executionId.split(':')
    let context = { graph: workflow, parent: null, instance: null, path: '' }
    for (const id of path.slice(0, -1)) {
      const instance = context.graph.nodes?.find((node) => sameId(node.id, id))
      const definition = instance && definitions.get(instance.type)
      if (!definition) { context = null; break }
      context = enter(context, instance, definition)
    }
    const writer = context?.graph.nodes?.find((node) => sameId(node.id, path.at(-1)))
    if (!writer || writer.type !== 'PromptHelperWriter') continue
    for (const field of FIELDS) {
      const resolved = primitiveValue(context, inputLink(context, writer, field), definitions)
      if (resolved && apiNode.inputs[field] !== resolved.value) {
        apiNode.inputs[field] = resolved.value
        repaired++
      }
    }
  }
  return repaired
}
