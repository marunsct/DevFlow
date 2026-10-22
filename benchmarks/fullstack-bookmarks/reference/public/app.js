const list = document.getElementById('list');
const filter = document.getElementById('filter');
let items = [];
async function refresh() { items = await (await fetch('/api/bookmarks')).json(); render(); }
function render() {
  list.innerHTML = '';
  items.filter((b) => !filter.value || b.tag === filter.value).forEach((b) => {
    const li = document.createElement('li');
    const a = document.createElement('a'); a.href = b.url; a.textContent = b.title;
    const tag = document.createElement('span'); tag.textContent = ` ${b.tag} `;
    const del = document.createElement('button'); del.textContent = 'Delete';
    del.onclick = async () => { await fetch(`/api/bookmarks/${b.id}`, { method: 'DELETE' }); refresh(); };
    li.append(a, tag, del); list.append(li);
  });
}
document.getElementById('add').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = { title: title.value, url: url.value, tag: tag.value };
  const response = await fetch('/api/bookmarks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (response.ok) e.target.reset();
  refresh();
});
filter.addEventListener('input', render);
refresh();
