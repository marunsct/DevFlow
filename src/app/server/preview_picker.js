// Point and say (plan WS.5): added to a preview's pages only through a link signed for pointing
// (`app.server.preview.PICKER_SCRIPT`). It outlines the element under the pointer and, when one is chosen, sends the
// run page what the page says of it: a short selector (its id, its test id, else a short path of positions), its tag,
// visible text, box and markup, each capped here and again by the run page and the server, which treat it as
// untrusted. The choice does not reach the page's own handlers. It runs only inside a frame, and sends to its parent.
(function () {
  if (window.parent === window) return;
  var SOURCE = 'devflow-preview-pick';
  var last = null;
  var kept = '';

  function escaped(value) {
    if (window.CSS && CSS.escape) return CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function unique(query) {
    try { return document.querySelectorAll(query).length === 1; } catch (error) { return false; }
  }

  function ownSelector(node) {
    if (node.id) {
      var byId = '#' + escaped(node.id);
      if (unique(byId)) return byId;
    }
    var testId = node.getAttribute('data-testid');
    if (testId) {
      var byTestId = '[data-testid="' + String(testId).replace(/["\\]/g, '\\$&') + '"]';
      if (unique(byTestId)) return byTestId;
    }
    return '';
  }

  function selectorOf(element) {
    var parts = [];
    var node = element;
    while (node && node.nodeType === 1 && parts.length < 8) {
      var own = ownSelector(node);
      if (own) { parts.unshift(own); break; }
      var tag = node.tagName.toLowerCase();
      if (tag === 'html' || tag === 'body') { parts.unshift(tag); break; }
      var position = 1;
      var sibling = node;
      while ((sibling = sibling.previousElementSibling)) {
        if (sibling.tagName === node.tagName) position++;
      }
      parts.unshift(tag + ':nth-of-type(' + position + ')');
      node = node.parentElement;
    }
    return parts.join(' > ').slice(0, 300);
  }

  function outline(element) {
    if (last && last.style) last.style.outline = kept;
    last = element;
    if (element && element.style) {
      kept = element.style.outline;
      element.style.outline = '2px solid Highlight';
    }
  }

  document.addEventListener('mouseover', function (event) {
    if (event.target && event.target.nodeType === 1) outline(event.target);
  }, true);

  document.addEventListener('click', function (event) {
    var element = event.target;
    if (!element || element.nodeType !== 1) return;
    event.preventDefault();
    event.stopPropagation();
    outline(null);
    var box = element.getBoundingClientRect();
    window.parent.postMessage({
      source: SOURCE,
      version: 1,
      element: {
        selector: selectorOf(element),
        tag: element.tagName.toLowerCase(),
        text: String(element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200),
        html: String(element.outerHTML || '').slice(0, 1000),
        box: { x: Math.round(box.left), y: Math.round(box.top), width: Math.round(box.width), height: Math.round(box.height) },
      },
    }, '*');
    outline(element);
  }, true);

  document.addEventListener('submit', function (event) {
    event.preventDefault();
    event.stopPropagation();
  }, true);
})();
