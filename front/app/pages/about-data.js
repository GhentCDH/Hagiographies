// @ts-check
/**
 * "About the data" page. Plain HTML in a JS module, so the page needs no
 * fetch and survives the single-file build. Asset URLs resolve against this
 * module (the compose step rewrites import.meta.url).
 */
import dataset from "../dataset.js";

const diagram = new URL("../assets/hagiographies_model.svg", import.meta.url).href;

export const html = /* html */ `
<h1>About the data</h1>
<p class="lead">This browser shows one published version of the Hagiographies database:
medieval Latin hagiographic texts, the manuscripts that transmit them, the codices
that hold those manuscripts, and the printed editions based on them. It is the
prototype corpus of the M-PATCH project at Ghent University.</p>

<h2>How this page works</h2>
<p>For publication the database is exported to a single SQLite file. That file
is deposited together with this page, and this page opens it in your browser:
every search, filter and count runs locally, on the embedded copy. Nothing is
sent to a server, apart from requests for IIIF images (see below).</p>

<h2>What is in it</h2>
<p>The core of the model is a chain from text to manuscript to codex, with editions
on the side.</p>
<dl class="entity-list">
  <dt>Text</dt>
  <dd>A hagiographic work: title, dating with a confidence level, form, source type
  and subtype, author, places of creation and destination. A text can be a
  <i>réécriture</i> (rewriting) of another text.</dd>
  <dt>Manuscript</dt>
  <dd>One copy of a text in a codex. It links a text to a codex and gives the folio
  or page range. Manuscripts can be related to each other ("based on exemplar",
  "exemplar of") and can carry their own links.</dd>
  <dt>Codex</dt>
  <dd>The physical book: shelfmark, holding institution and location, dimensions,
  dating, preservation status, type, origin and provenance (each with a confidence
  level), vernacular region, and flags for the Légendiers project and for composite
  codices. Typed links describe the whole codex: catalogue descriptions, Légendiers
  entries, IIIF manifests and scans. The number of copies in a codex is derived
  from its manuscripts.</dd>
  <dt>Edition</dt>
  <dd>A printed edition of a text: the publication it appears in, page numbers,
  collation, notes and links. An edition can be a reprint of another edition, and
  it records which earlier editions it consulted.</dd>
  <dt>Publication</dt>
  <dd>The book or journal volume that contains an edition: identifier, year and full
  bibliographic reference.</dd>
  <dt>Edition and manuscript</dt>
  <dd>Which manuscripts an edition used. Each pair is recorded once.</dd>
  <dt>Text and repertory</dt>
  <dd>Where a text is listed in reference repertories, with a link when there is
  one.</dd>
  <dt>Places</dt>
  <dd>Locations (with latitude and longitude, where known), institutions, dioceses
  and archdioceses. They describe where texts were written and for whom, and
  where codices come from and are kept.</dd>
  <dt>Authors and lookups</dt>
  <dd>Authors with their milieu, and short controlled lists (text form, source type,
  codex type, preservation status, confidence levels, link types) that keep values
  consistent.</dd>
</dl>

<figure class="model-diagram">
  <a href="${diagram}" target="_blank" rel="noopener">
    <img src="${diagram}" loading="lazy" decoding="async"
      alt="Entity diagram of the Hagiographies database: every table with its columns, and lines for the foreign keys between them.">
  </a>
  <figcaption>The full database model. Open the diagram on its own to zoom in.</figcaption>
</figure>

<h2>Identifiers</h2>
<p>Texts, manuscripts and editions have readable identifiers that build on each
other. They are unique regardless of case.</p>
<div class="table-scroll" role="region" aria-labelledby="identifier-caption" tabindex="0">
<table>
  <caption id="identifier-caption">Identifier formats</caption>
  <thead><tr><th scope="col">Entity</th><th scope="col">Format</th><th scope="col">Examples</th></tr></thead>
  <tbody>
    <tr><th scope="row">Text</th><td><code>BHL</code> or <code>NO_BHL</code>, an underscore, then the BHL number or another unique id</td><td><code>BHL_29</code>, <code>NO_BHL_ALPER</code></td></tr>
    <tr><th scope="row">Manuscript</th><td>The text identifier, a hyphen, then a copy number</td><td><code>BHL_29-4</code></td></tr>
    <tr><th scope="row">Edition</th><td>The text identifier, a hyphen, then a letter</td><td><code>BHL_29-A</code></td></tr>
  </tbody>
</table>
</div>
<p>BHL is the <i>Bibliotheca Hagiographica Latina</i>, the standard repertory of
Latin hagiography. Texts without a BHL number get a <code>NO_BHL</code> identifier.</p>

<h2>IIIF images</h2>
<p>Where a holding institution publishes digitised images of a codex through IIIF,
the codex links to that institution's IIIF manifest. The viewer on a codex page
loads the manifest and the images live, from the institution's own servers. They
are not part of this dataset, and their rights and terms of use remain with the
holding institution. If an institution changes or withdraws a manifest, the viewer
shows what that server returns.</p>

<h2>What this public view leaves out</h2>
<p>A few links in the working database are not shown here:</p>
<ul>
  <li>links to the restricted M-PATCH working files (scans on the project's internal
  file server, which are not public);</li>
  <li>placeholder links that only mark that a link still has to be found.</li>
</ul>
<p>These links are removed from the in-memory copy when the page opens the database,
before anything is displayed. The deposited SQLite file is the unmodified export.</p>

<h2>Licences</h2>
<ul>
  <li>Data: <a href="${dataset.licence.dataUrl}" target="_blank" rel="noopener">${dataset.licence.data}</a>.
  Please cite the dataset when you use it (see the front page).</li>
  <li>Code of this browser: <a href="${dataset.licence.codeUrl}" target="_blank" rel="noopener">${dataset.licence.code}</a>.
  Third-party components keep their own licences; see the <a href="#/en/page/credits">credits</a>.</li>
  <li>Not covered: ${dataset.licence.excluded}. IIIF images remain under the terms
  of their holding institutions.</li>
</ul>
`;

export const menu = { id: "about-data", label: "About the data", html };
