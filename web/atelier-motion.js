/* Lightweight page enhancement for agent colors. The interface works without this script. */
(() => {
  "use strict";
  const markAgents = () => {
    document.querySelectorAll('a[href^="/tools/"]').forEach(link => {
      const match = link.getAttribute('href')?.match(/^\/tools\/(conflicts|clauses|confidentiality|litigation)$/);
      const card = link.closest('.lens-card,.workspace-card,.workspace-tile,.service-card,.agent-report');
      if (match && card) card.dataset.agent = match[1];
    });
    const tool = document.body.dataset.page?.match(/^tools-(conflicts|clauses|confidentiality|litigation)$/);
    if (tool) document.querySelector('.tool-page')?.setAttribute('data-agent', tool[1]);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markAgents, {once: true});
  } else {
    markAgents();
  }
})();
