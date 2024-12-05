/*

Abandoned. Kept getting incomprehensible error: [...] TypeError: this.window.requestAnimationFrame is not a function. [...]
Apparently an open issue for bun: https://github.com/oven-sh/bun/issues/11797

Oh well. Node + jsdom will have to do.
*/

import { Window } from "happy-dom";

const file = Bun.file(process.argv[2]);
const html = await file.text();

const window = new Window();
window.document.write(html); // or document.content = html; ??
await window.happyDOM.waitUntilComplete();

window.addEventListener("load", () => {
  const reactContext = window.netflix.reactContext;
  const sectionData = reactContext.models.nmTitleUI.data.sectionData;
  console.log(JSON.stringify(sectionData));
});

await window.happyDOM.close();