// @ts-check
/**
 * Credits page: project, team, partners, funding, citation and third-party
 * software. Plain HTML in a JS module (no fetch).
 *
 * Third-party licences were checked against the vendored LICENSE files and
 * THIRD-PARTY-NOTICES.md in front/vendor/pihka (Pihka at d1cc57f).
 */
import dataset, { citeDataset } from "../dataset.js";

const ext = (href, text) => `<a href="${href}" target="_blank" rel="noopener">${text}</a>`;

export const html = /* html */ `
<h1>Credits</h1>

<h2>M-PATCH</h2>
<p>This dataset is the prototype corpus of <b>M-PATCH</b>, the
<i>Multidisciplinary Platform for Annotating Textual Corpora and Histories — A Reusable
Modular Framework for Tracing Patterns and Change in the Living Material Record of
Historical Texts Through Linked Data</i>.</p>
<p>M-PATCH is a medium-scale research infrastructure project funded by the Research
Foundation – Flanders (FWO), project I004326N, running from 1 May 2026 to 30 April
2030. Project website: ${ext("https://m-patch.ugent.be/en", "m-patch.ugent.be")}.</p>

<h2>Team</h2>
<dl class="people">
  <dt>Promoter-spokesperson</dt>
  <dd>Steven Vanderputten (Department of History)</dd>
  <dt>Co-promoters</dt>
  <dd>Anne Breitbarth (Department of Linguistics, DiaLing)</dd>
  <dd>Julie Birkholz (Department of History / GhentCDH)</dd>
  <dd>Els Lefever (LT3, Department of Translation, Interpreting and Communication)</dd>
  <dd>Klaas Bentein (Department of Linguistics)</dd>
  <dd>Koen De Temmerman (Department of Literary Studies)</dd>
  <dd>Hendrik Defoort (Ghent University Library)</dd>
  <dt>Project manager</dt>
  <dd><!-- confirm before release -->Lien Hellebaut</dd>
  <dt>Researchers in affiliated projects</dt>
  <dd><!-- confirm before release -->Fiammetta Comelli</dd>
  <dd><!-- confirm before release -->Francesca Digiaro</dd>
  <dd><!-- confirm before release -->Valentina Lunardi</dd>
  <dt>Software and digital consultancy (GhentCDH)</dt>
  <dd><!-- confirm before release -->Joren Six</dd>
  <dd><!-- confirm before release -->Sibren Wieme</dd>
  <dd><!-- confirm before release -->Miel Peeters</dd>
</dl>

<h2>Partners</h2>
<ul>
  <li>Société des Bollandistes</li>
  <li>KBR (Royal Library of Belgium)</li>
  <li>Public Library of Bruges</li>
  <li>Université libre de Bruxelles</li>
</ul>
<p>Related project: the FWO senior research project <i>Hagiographic Entanglements of
the Long Tenth Century</i>.</p>

<h2>Ghent Centre for Digital Humanities</h2>
<p>This work was supported in part by the Ghent Centre for Digital Humanities
(GhentCDH), core facility of Ghent University
(${ext("https://www.ghentcdh.ugent.be", "www.ghentcdh.ugent.be")}).</p>
<p>GhentCDH provided software development and digital consultancy for the project.</p>

<h2>How to cite</h2>
<p>The dataset:</p>
<blockquote class="citation">${citeDataset(dataset)}</blockquote>
<p>The M-PATCH approach:</p>
<blockquote class="citation">${dataset.paper.text}
${ext(dataset.paper.url, dataset.paper.url)}</blockquote>

<h2>Software</h2>
<p>This browser is built with ${ext("https://github.com/GhentCDH/Pihka", "Pihka")}
(GhentCDH, MIT licence), a toolkit for publishing SQLite research data as a static
website. It includes the following third-party components, each under its own
licence:</p>
<div class="table-scroll" role="region" aria-labelledby="software-caption" tabindex="0">
<table>
  <caption id="software-caption">Third-party software</caption>
  <thead><tr><th scope="col">Component</th><th scope="col">Used for</th><th scope="col">Licence</th></tr></thead>
  <tbody>
    <tr><th scope="row">${ext("https://github.com/tify-iiif-viewer/tify", "TIFY")} 0.36</th><td>IIIF image viewer</td><td>AGPL-3.0</td></tr>
    <tr><th scope="row">${ext("https://openseadragon.github.io/", "OpenSeadragon")} 5.0 (bundled in TIFY)</th><td>Deep-zoom image display</td><td>BSD-3-Clause</td></tr>
    <tr><th scope="row">${ext("https://maplibre.org/", "MapLibre GL JS")} 6.14</th><td>Maps</td><td>BSD-3-Clause</td></tr>
    <tr><th scope="row">${ext("https://github.com/protomaps/PMTiles", "PMTiles")} 4.5</th><td>Map tiles from a single file</td><td>BSD-3-Clause</td></tr>
    <tr><th scope="row">${ext("https://github.com/101arrowz/fflate", "fflate")}</th><td>Decompression for map tiles</td><td>MIT</td></tr>
    <tr><th scope="row">${ext("https://sqlite.org/wasm", "SQLite Wasm")} 3.53</th><td>The database engine, in the browser</td><td>SQLite: public domain; npm package: Apache-2.0</td></tr>
    <tr><th scope="row">${ext("https://preactjs.com/", "Preact")} 11</th><td>User interface</td><td>MIT</td></tr>
    <tr><th scope="row">${ext("https://github.com/anyblades/blades", "Blades")} (Pico CSS fork)</th><td>Base stylesheet</td><td>MIT</td></tr>
  </tbody>
</table>
</div>
<p>The UGent Panno typeface and the GhentCDH logo belong to Ghent University. They are
not covered by the data or code licences.</p>
`;

export const menu = { id: "credits", label: "Credits", html };
