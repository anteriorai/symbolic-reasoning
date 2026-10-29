(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const data = JSON.parse($("history-data").textContent);
  const graph = data.graph;
  const symbols = { ...graph.predicates, ...graph.aggregators, ...graph.outcomes,
    Root: { id: "Root", type: "Root", label: "Start" } };
  let step = 0;
  let answers = data.initial_answers;
  let selected = null, selectedTrace = null, timer = null;
  let scale = 1, offsetX = 0, offsetY = 0, layoutWidth = 0, layoutHeight = 0;
  let followReplay = false, focusedStep = null;
  const cards = new Map(), edges = new Map(), badges = [], rows = [];
  const traceControls = [];
  const dependencies = new Map();
  const graphItems = new Set(Object.values(graph.nodes).map(node => node.item_id));
  const statusHints = {
    Unanswered: "No answer has been recorded for this predicate at this step.",
    Undecided: "This expression does not yet have enough recorded answers to determine Yes or No."
  };
  const frame = () => data.frames[step];
  const label = id => {
    const s = symbols[id];
    if (s.label || s.name || s.question || s.description) return s.label || s.name || s.question || s.description;
    if (s.type !== "Aggregator") return s.id;
    if (s.strategy.type === "AllStrategy") {
      if (!s.truth_value && s.argument_ids.length === 1) return `Not: ${label(s.argument_ids[0])}`;
      return s.truth_value ? "All conditions" : "All conditions are No";
    }
    return rule(s);
  };
  function rule(symbol) {
    const names = { AllStrategy: "ALL", AtLeastStrategy: "AT LEAST", AtMostStrategy: "AT MOST", ExactlyStrategy: "EXACTLY" };
    return `${names[symbol.strategy.type]}${symbol.strategy.count === undefined ? "" : ` ${symbol.strategy.count}`} · ${symbol.truth_value ? "Yes" : "No"}`;
  }
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(text, className, onClick) {
    const node = element("button", className, text);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }
  function badge(value, pending = "Unanswered") {
    const node = element("span", `badge ${value === true ? "yes" : value === false ? "no" : ""}`, value === true ? "Yes" : value === false ? "No" : pending);
    node.title = statusHints[node.textContent] || "";
    return node;
  }
  function symbolDependencies(id) {
    if (!dependencies.has(id)) {
      const symbol = symbols[id];
      dependencies.set(id, new Set(symbol.type === "Aggregator"
        ? symbol.argument_ids.flatMap(child => [...symbolDependencies(child)])
        : symbol.type === "Predicate" ? [id] : []));
    }
    return dependencies.get(id);
  }
  function inspect(id) { selected = id; selectedTrace = null; render(); }
  function addBadge(container, id, outcomeNode = null) {
    const node = badge(null, outcomeNode ? "Not reached" : symbols[id].type === "Aggregator" ? "Undecided" : "Unanswered");
    container.append(node);
    badges.push({ node, id, outcomeNode });
  }
  function addRequirements(container, id, seen) {
    for (const childId of symbols[id].argument_ids) {
      const child = symbols[childId];
      const nested = child.type === "Aggregator";
      const external = graphItems.has(childId);
      const shared = nested && (seen.has(childId) || external);
      const row = button("", `requirement ${nested ? "nested" : external ? "reference" : "leaf"}`, () => inspect(childId));
      if (external) row.title = "Shown in its own graph card. Click to inspect.";
      row.dataset.symbolId = childId;
      const text = element("span", "row-label");
      text.append(element("span", "requirement-name", label(childId)));
      if (nested) text.append(element("span", "requirement-rule", rule(child)));
      row.append(text);
      addBadge(row, childId);
      rows.push({ node: row, id: childId });
      if (nested) {
        const group = element("section", `requirement-group${shared ? " shared" : ""}`);
        group.dataset.symbolId = childId;
        group.setAttribute("aria-label", label(childId));
        group.append(row);
        container.append(group);
        if (shared) {
          row.title = external ? "Shared expression shown in its own graph card. Click to inspect its requirements." : "Shared expression shown elsewhere in this card. Click to inspect its requirements.";
        } else {
          // Expanding every occurrence of a shared expression can grow exponentially.
          seen.add(childId);
          const children = element("div", "requirement-children");
          group.append(children);
          addRequirements(children, childId, seen);
        }
      } else container.append(row);
    }
  }
  function svg(tag, attributes = {}) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  }
  function pathThrough(points) {
    points = points.filter((point, index) => !index || point.x !== points[index - 1].x || point.y !== points[index - 1].y);
    let path = `M ${points[0].x} ${points[0].y}`;
    for (let index = 1; index < points.length - 1; index++) {
      const previous = points[index - 1], point = points[index], next = points[index + 1];
      const before = Math.hypot(point.x - previous.x, point.y - previous.y);
      const after = Math.hypot(next.x - point.x, next.y - point.y);
      const radius = Math.min(12, before / 2, after / 2);
      path += ` L ${point.x + (previous.x - point.x) * radius / before} ${point.y + (previous.y - point.y) * radius / before}`;
      path += ` Q ${point.x} ${point.y} ${point.x + (next.x - point.x) * radius / after} ${point.y + (next.y - point.y) * radius / after}`;
    }
    const last = points[points.length - 1];
    return `${path} L ${last.x} ${last.y}`;
  }
  function buildGraph() {
    $("cards").replaceChildren();
    $("edges").replaceChildren();
    const defs = svg("defs");
    for (const [id, color] of [["arrow", "#b8c8c0"], ["arrow-active", "#17766d"]]) {
      const marker = svg("marker", { id, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" });
      marker.append(svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color }));
      defs.append(marker);
    }
    $("edges").append(defs);
    const layout = new dagre.graphlib.Graph({ multigraph: true });
    layout.setGraph({ rankdir: "TB", nodesep: 16, edgesep: 4, ranksep: 35, marginx: 25, marginy: 15 });
    layout.setDefaultEdgeLabel(() => ({}));
    for (const [id, node] of Object.entries(graph.nodes)) {
      const symbol = symbols[node.item_id];
      const card = element("div", `card execution-card ${symbol.type.toLowerCase()}`);
      card.dataset.nodeId = id;
      card.dataset.symbolId = symbol.id;
      const header = button("", "card-header", () => inspect(symbol.id));
      const kind = element("span", "card-kind");
      kind.append(element("span", "", symbol.type === "Aggregator" ? rule(symbol) : symbol.type.toUpperCase()));
      if (symbol.type !== "Root") addBadge(kind, symbol.id, symbol.type === "Outcome" ? id : null);
      header.append(kind, element("span", "card-title", label(symbol.id)));
      card.append(header);
      if (symbol.type === "Aggregator") {
        const requirements = element("div", "requirements");
        addRequirements(requirements, symbol.id, new Set([symbol.id]));
        card.append(requirements);
      }
      $("cards").append(card);
      cards.set(id, card);
      layout.setNode(id, { width: card.offsetWidth, height: card.offsetHeight });
    }
    for (const [id, edge] of Object.entries(graph.edges)) {
      layout.setEdge(edge.source, edge.target, { width: edge.source === "Root" && edge.condition ? 0 : 28, height: 16 }, id);
    }
    dagre.layout(layout);
    layoutWidth = layout.graph().width;
    layoutHeight = layout.graph().height;
    $("world").style.width = `${layoutWidth}px`;
    $("world").style.height = `${layoutHeight}px`;
    $("edges").setAttribute("width", layoutWidth);
    $("edges").setAttribute("height", layoutHeight);
    for (const [id, card] of cards) {
      const node = layout.node(id);
      card.style.left = `${node.x - node.width / 2}px`;
      card.style.top = `${node.y - node.height / 2}px`;
    }
    for (const [id, edge] of Object.entries(graph.edges)) {
      const placed = layout.edge({ v: edge.source, w: edge.target, name: id });
      const path = svg("path", { class: "edge", "data-edge-id": id, d: pathThrough(placed.points), "marker-end": "url(#arrow)" });
      const text = svg("text", { class: "edge-label", x: placed.x, y: placed.y + 4, "text-anchor": "middle" });
      text.textContent = edge.source === "Root" && edge.condition ? "" : edge.condition ? "Yes" : "No";
      $("edges").append(path, text);
      edges.set(id, { path, text });
    }
    $("graph-count").textContent = `${cards.size} nodes · ${Object.keys(graph.predicates).length} predicates`;
  }
  function transform() { $("world").style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`; }
  function fit() {
    const view = $("viewport");
    scale = Math.min((view.clientWidth - 35) / layoutWidth, (view.clientHeight - 25) / layoutHeight, 1.15);
    offsetX = (view.clientWidth - layoutWidth * scale) / 2;
    offsetY = (view.clientHeight - layoutHeight * scale) / 2;
    transform();
  }
  function zoom(factor, x = $("viewport").clientWidth / 2, y = $("viewport").clientHeight / 2) {
    setFollow(false);
    const nextScale = Math.min(2.5, Math.max(.08, scale * factor));
    offsetX = x - (x - offsetX) * nextScale / scale;
    offsetY = y - (y - offsetY) * nextScale / scale;
    scale = nextScale;
    transform();
  }
  function setFollow(enabled) {
    followReplay = enabled;
    $("follow").setAttribute("aria-pressed", String(enabled));
    if (enabled) focusFrame();
  }
  function focusFrame() {
    focusedStep = step;
    let targets = [...cards.values()].filter(card => card.classList.contains("changed"));
    if (!targets.length) targets = frame().reached
      .filter(id => symbols[graph.nodes[id].item_id].type !== "Root" && frame().verdicts[graph.nodes[id].item_id] == null)
      .map(id => cards.get(id));
    if (!targets.length) return;
    const left = Math.min(...targets.map(card => card.offsetLeft));
    const top = Math.min(...targets.map(card => card.offsetTop));
    const right = Math.max(...targets.map(card => card.offsetLeft + card.offsetWidth));
    const bottom = Math.max(...targets.map(card => card.offsetTop + card.offsetHeight));
    const view = $("viewport");
    scale = Math.min((view.clientWidth - 50) / (right - left), (view.clientHeight - 50) / (bottom - top), 1);
    offsetX = (view.clientWidth - (left + right) * scale) / 2;
    offsetY = (view.clientHeight - (top + bottom) * scale) / 2;
    transform();
  }
  function textSection(container, title, text) {
    if (!text) return;
    container.append(element("h3", "", title), element("p", "", text));
  }
  function answerLink(id) {
    const row = button(label(id), "answer-link", () => inspect(id));
    row.prepend(badge(frame().verdicts[id], symbols[id].type === "Aggregator" ? "Undecided" : "Unanswered"));
    return row;
  }
  function traceList(container, traces, kind, outcomeId = null) {
    traces.forEach((trace, index) => {
      if (outcomeId && trace.outcome !== outcomeId) return;
      const name = outcomeId ? `Path ${index + 1}` : trace.outcome ? label(trace.outcome) : `Explored path ${index + 1}`;
      const content = element("div");
      const control = button(`${name} · ${trace.steps.length} answers`, "trace-link", () => {
        const active = selectedTrace?.kind === kind && selectedTrace.index === index;
        selectedTrace = active ? null : { kind, index };
        renderTraceSelection();
        renderGraph();
      });
      control.setAttribute("aria-expanded", "false");
      container.append(control, content);
      traceControls.push({ control, content, trace, kind, index });
    });
  }
  function renderTraceSelection() {
    for (const { control, content, trace, kind, index } of traceControls) {
      const active = selectedTrace?.kind === kind && selectedTrace.index === index;
      control.setAttribute("aria-expanded", String(active));
      control.classList.toggle("active", active);
      content.replaceChildren();
      if (active) {
        if (!trace.steps.length) content.append(element("p", "note", "This path needed no predicate answers."));
        for (const id of trace.steps) {
          const row = element("div", "trace-step");
          row.append(badge(answers[id].is_met), button(label(id), "", () => inspect(id)));
          row.append(element("p", "", answers[id].reasoning || "No reasoning supplied."));
          content.append(row);
        }
      }
    }
  }
  function renderInspector() {
    const container = $("inspector");
    container.replaceChildren();
    traceControls.length = 0;
    const f = frame();
    if (selected && selected !== "Root") {
      const symbol = symbols[selected];
      container.append(element("h2", "", label(selected)), element("div", "identifier", `${symbol.type} · ${symbol.id}`));
      if (symbol.type === "Predicate") {
        textSection(container, "Question", symbol.question);
        const answer = answers[selected];
        container.append(element("h3", "", "Answer"), badge(answer?.is_met));
        textSection(container, "Reasoning", answer ? answer.reasoning || "No reasoning supplied." : "No answer recorded at this step.");
        textSection(container, "Guidance", symbol.context);
        if (answer) {
        }
      } else if (symbol.type === "Aggregator") {
        container.append(element("h3", "", "Expression"), badge(f.verdicts[selected], "Undecided"));
        textSection(container, "Rule", `${rule(symbol)}: count arguments whose value is ${symbol.truth_value ? "Yes" : "No"}.`);
        for (const id of symbol.argument_ids) container.append(answerLink(id));
      } else {
        textSection(container, "Outcome", symbol.description);
        const reached = f.reached.some(id => graph.nodes[id].item_id === selected);
        container.append(element("p", "note", reached ? "Reached at this step." : "Not reached at this step."));
        if (f.trace) {
          container.append(element("h3", "", "Reasoning traces"));
          const traces = f.trace.outcome_paths;
          traceList(container, traces, "outcome_paths", selected);
          if (!traces.some(t => t.outcome === selected)) container.append(element("p", "note", "No completed path reaches this outcome."));
        } else container.append(element("p", "note", "Reasoning traces are available once the execution is resolved."));
      }
      textSection(container, "Documentation", symbol.doc);
      for (const id of symbol.citation_ids || []) {
        const citation = graph.citations?.[id];
        if (citation) textSection(container, `Source · ${citation.filename || citation.source_ref}`, citation.excerpt || citation.source_ref);
      }
      return;
    }
    container.append(element("h2", "", "Follow the reasoning"), element("p", "note", "Step through applied answers and see how the policy reaches a decision."));
    const status = element("div", "status-block");
    status.append(element("strong", "", f.resolved ? "Decision resolved" : "Decision unresolved"), element("span", "", `${Object.keys(answers).length} of ${Object.keys(graph.predicates).length} predicates answered`));
    container.append(status);
    textSection(container, "Policy", graph.policy_context);
    if (f.applied.length) {
      container.append(element("h3", "", "Applied this batch"));
      f.applied.forEach(id => container.append(answerLink(id)));
    } else if (step === 0 && Object.keys(answers).length) {
      container.append(element("h3", "", "Initial answers"));
      Object.keys(answers).forEach(id => container.append(answerLink(id)));
    }
    if (f.trace) {
      container.append(element("h3", "", "Outcome traces"));
      if (!f.trace.outcome_paths.length) container.append(element("p", "note", "Resolved without reaching an outcome."));
      traceList(container, f.trace.outcome_paths, "outcome_paths");
      const details = element("details");
      details.append(element("summary", "note", `All explored paths (${f.trace.all_paths.length})`));
      traceList(details, f.trace.all_paths, "all_paths");
      container.append(details);
      container.append(element("p", "note", "Traces show recorded answers along each explored path, including answers beyond those needed to decide."));
    } else container.append(element("p", "note", "Reasoning traces appear when the decision is resolved. An unanswered predicate can remain unanswered when a condition short-circuits."));
  }
  function renderGraph() {
    const f = frame();
    const applied = new Set(f.applied), reached = new Set(f.reached), taken = new Set(f.taken);
    const previouslyTaken = new Set(data.frames[Math.max(0, step - 1)].taken);
    const newOutcomeNodes = new Set();
    // Shared outcomes can be reached by another branch in a later batch.
    for (const id of taken) {
      const target = graph.edges[id].target;
      if (!previouslyTaken.has(id) && symbols[graph.nodes[target].item_id].type === "Outcome") newOutcomeNodes.add(target);
    }
    const trace = selectedTrace && f.trace?.[selectedTrace.kind]?.[selectedTrace.index];
    const highlighted = new Set(trace?.steps || []);
    const affected = id => [...symbolDependencies(id)].some(p => applied.has(p));
    const traced = id => [...symbolDependencies(id)].some(p => highlighted.has(p));
    for (const [nodeId, card] of cards) {
      const symbolId = graph.nodes[nodeId].item_id;
      card.classList.toggle("reached", reached.has(nodeId));
      card.classList.toggle("changed", affected(symbolId) || newOutcomeNodes.has(nodeId));
      card.classList.toggle("selected", selected === symbolId);
      card.classList.toggle("in-trace", traced(symbolId) || trace?.outcome === symbolId);
    }
    for (const { node, id } of rows) {
      node.classList.toggle("changed", affected(id));
      node.classList.toggle("selected", selected === id);
      node.classList.toggle("in-trace", traced(id));
    }
    for (const { node, id, outcomeNode } of badges) {
      const value = f.verdicts[id];
      node.className = `badge ${outcomeNode ? reached.has(outcomeNode) ? "yes" : "" : value === true ? "yes" : value === false ? "no" : ""}`;
      node.textContent = outcomeNode ? reached.has(outcomeNode) ? "Reached" : "Not reached" : value === true ? "Yes" : value === false ? "No" : symbols[id].type === "Aggregator" ? "Undecided" : "Unanswered";
      node.title = statusHints[node.textContent] || "";
    }
    for (const [id, { path, text }] of edges) {
      path.classList.toggle("taken", taken.has(id));
      text.classList.toggle("taken", taken.has(id));
      path.setAttribute("marker-end", taken.has(id) ? "url(#arrow-active)" : "url(#arrow)");
    }
  }
  function render() {
    // Rebuild from recorded batches so backward seeks and corrections agree.
    answers = Object.assign(Object.create(null), data.initial_answers);
    for (let index = 0; index < step; index++) Object.assign(answers, data.batches[index]);
    renderGraph();
    const f = frame();
    $("timeline").max = data.frames.length - 1;
    $("timeline").value = step;
    $("timeline").setAttribute("aria-valuetext", step === 0 ? "Initial state" : `Batch ${step}`);
    $("step-label").textContent = step === 0 ? "Initial state" : `Batch ${step} of ${data.frames.length - 1}`;
    $("run-status").textContent = f.resolved ? "Decision resolved" : "Decision unresolved";
    $("previous").disabled = step === 0;
    $("next").disabled = step === data.frames.length - 1;
    $("play").disabled = data.frames.length === 1;
    $("batch-summary").textContent = step === 0 ? "Starting snapshot · playback follows batch order, not elapsed time" : f.applied.length ? `${f.applied.length} answer${f.applied.length === 1 ? "" : "s"} applied` : "Empty batch · no answers applied";
    renderInspector();
    if (followReplay && focusedStep !== step) focusFrame();
  }
  function pause() {
    clearTimeout(timer); timer = null;
    $("play").textContent = "Play";
    $("play").setAttribute("aria-label", "Play recording");
  }
  function goTo(nextStep) {
    selectedTrace = null; pause();
    step = Math.max(0, Math.min(data.frames.length - 1, nextStep)); render();
  }
  function tick() {
    if (step >= data.frames.length - 1) { pause(); return; }
    timer = setTimeout(() => { step++; selectedTrace = null; render(); tick(); }, 1000);
  }
  $("play").onclick = () => {
    if (timer !== null) { pause(); return; }
    if (step === data.frames.length - 1) step = 0;
    selectedTrace = null; render();
    $("play").textContent = "Pause"; $("play").setAttribute("aria-label", "Pause playback"); tick();
  };
  $("previous").onclick = () => goTo(step - 1);
  $("next").onclick = () => goTo(step + 1);
  $("timeline").oninput = event => goTo(Number(event.target.value));
  $("overview").onclick = () => { selected = null; selectedTrace = null; render(); };
  $("follow").onclick = () => setFollow(!followReplay);
  $("fit").onclick = () => { setFollow(false); fit(); };
  $("zoom-in").onclick = () => zoom(1.2);
  $("zoom-out").onclick = () => zoom(1 / 1.2);
  const viewport = $("viewport");
  viewport.addEventListener("wheel", event => {
    event.preventDefault();
    const bounds = viewport.getBoundingClientRect();
    zoom(Math.exp(-event.deltaY * .002), event.clientX - bounds.left, event.clientY - bounds.top);
  }, { passive: false });
  let drag = null;
  viewport.addEventListener("pointerdown", event => {
    if (event.target.closest("button") || event.button !== 0) return;
    drag = { x: event.clientX, y: event.clientY, offsetX, offsetY };
    viewport.setPointerCapture(event.pointerId); viewport.classList.add("dragging");
  });
  viewport.addEventListener("pointermove", event => {
    if (!drag) return;
    setFollow(false);
    offsetX = drag.offsetX + event.clientX - drag.x; offsetY = drag.offsetY + event.clientY - drag.y; transform();
  });
  const endDrag = () => { drag = null; viewport.classList.remove("dragging"); };
  viewport.addEventListener("pointerup", endDrag);
  viewport.addEventListener("pointercancel", endDrag);
  viewport.addEventListener("keydown", event => {
    if (event.target !== viewport) return;
    const moves = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] };
    if (moves[event.key]) { event.preventDefault(); setFollow(false); offsetX += moves[event.key][0]; offsetY += moves[event.key][1]; transform(); }
  });
  buildGraph(); render(); fit();
  if (scale < .45 && layoutHeight > layoutWidth * 2) setFollow(true);
})();
