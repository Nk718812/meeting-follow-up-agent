const notes = document.querySelector("#notes");
const analyze = document.querySelector("#analyze");
const count = document.querySelector("#count");
const error = document.querySelector("#error");
const status = document.querySelector("#status");
const results = document.querySelector("#results");

notes.addEventListener("input", () => { count.textContent = `${notes.value.length.toLocaleString()} characters`; });

function fillList(selector, items, emptyText) {
  const list = document.querySelector(selector);
  list.replaceChildren();
  (items.length ? items : [emptyText]).forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    if (!items.length) li.className = "empty";
    list.append(li);
  });
}

analyze.addEventListener("click", async () => {
  error.hidden = true;
  results.hidden = true;
  if (!notes.value.trim()) { error.textContent = "Please paste meeting notes before analyzing."; error.hidden = false; return; }
  status.hidden = false; analyze.disabled = true;
  try {
    const response = await fetch("/api/analyze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({notes: notes.value})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Analysis failed.");
    fillList("#decisions", data.decisions, "No explicit decisions found.");
    fillList("#questions", data.unresolved_questions, "No unresolved questions found.");
    fillList("#clarifications", data.clarifications, "");
    document.querySelector("#clarifications-wrap").hidden = !data.clarifications.length;
    const tbody = document.querySelector("#actions"); tbody.replaceChildren();
    if (!data.action_items.length) {
      const row = tbody.insertRow(); const cell = row.insertCell(); cell.colSpan = 3; cell.className = "empty"; cell.textContent = "No explicit action items found.";
    } else data.action_items.forEach((item) => {
      const row = tbody.insertRow();
      [item.task, item.owner, item.deadline].forEach((value, index) => { const cell = row.insertCell(); cell.textContent = value; if (index && ["Unassigned", "Not specified"].includes(value)) cell.className = "missing"; });
    });
    document.querySelector("#email").textContent = data.follow_up_email;
    const quality = document.querySelector("#quality");
    quality.textContent = data.quality_check.revised ? "Quality checked · Revised" : "Quality check passed";
    results.hidden = false; results.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (err) { error.textContent = err.message; error.hidden = false; }
  finally { status.hidden = true; analyze.disabled = false; }
});

document.querySelector("#copy").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(document.querySelector("#email").textContent);
  event.currentTarget.textContent = "Copied";
  setTimeout(() => { event.currentTarget.textContent = "Copy draft"; }, 1500);
});
