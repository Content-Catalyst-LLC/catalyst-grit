const form = document.getElementById('event-form');
if (form) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = document.getElementById('kind').value;
    const note = document.getElementById('note').value;
    const res = await fetch('/api/event', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ kind, note })
    });
    if (res.ok) location.reload();
    else alert('Error adding event');
  });
}
