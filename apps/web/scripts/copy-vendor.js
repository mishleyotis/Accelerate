// Copy the React UMD production builds the prototype modules run against
// (classic scripts on window.React/ReactDOM — the prototype's own model).
const fs = require("fs");
const path = require("path");

const out = path.join(__dirname, "..", "public", "vendor");
fs.mkdirSync(out, { recursive: true });
for (const [pkg, file] of [
  ["react", "react.production.min.js"],
  ["react-dom", "react-dom.production.min.js"],
]) {
  // umd/ is shipped but not in the package's exports map — resolve by path.
  const src = path.join(require.resolve(`${pkg}/package.json`), "..", "umd", file);
  fs.copyFileSync(src, path.join(out, file));
  console.log("vendor:", file);
}
