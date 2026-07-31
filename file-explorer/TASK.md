# Hagiographies Managed File Explorer

This part of the repository should contain a very simple web app for managing files on a network share
in such a way that users can't do much wrong.

The database has columns of type url which should be able to link to files on the network share.
Job students will do some data cleaning etc. on the database and they'll add links to these network share files to it.

I need to have a sort of managed file explorer interface in which they can rename / move files already on the share, and
upload new files to the share too.

Behind the scenes, these files are to be tracked in a 'files' table in the administator's hagio_admin schema.
That table should have a UUIDv4 for each of the tracked files and a column that tracks where it lives on the network share (a path relative to the network share's root).

i envision an interface that looks like this:

Of course, renaming updates the 'files' table accordingly, as do file moves and uploads.
Uploads should actually move the file to the network share, and first prompt for the name of the file.
Files are always uploaded to where the user is in the file explorer at that time.

The link button should generate a link to where this web app is deployed (will be https://files.m-patch.ugent.be/<something>) which allows either looking at the file in the browser (pdf, images, ...) or downloading the file onto the user's computer.

Now i know this sort of feels redundant: why would we need this web url which resolves to a network share location behind the scenes when we already have the files table that keeps track of where that file lives?

Users will interact with the database through mathesar. Making these links ensures that they can click on them and open the files, without having to e.g. mount the share.
It would be nice though if there was an extra table that somehow automatically links between the 'files' table and the rows in the database where we link to the file on files.m-patch.ugent.be
But i'm not sure how this would work, since students will just be:

- using the file explorer to find / create files
- clicking the link button to copy a working link to this file at files.m-patch.ugent.be to their clipboard
- going to mathesar and filling in this link at the correct location in the database
  - these locations are manuscript_link.url and edition_link.url

So the 'linking' happens on a logical level... i'm not sure how to solve for that.

# Stack

I'd like you to use the stack that i also use here: /home/miepeete/Projects/personal/trustmebro/.
except for the capacitor part (no app will be needed, just a web app).

Not everything needs to be copied, this will be way simpler.
No authentication (will be handled in caddy sitting in front of this site), therefore also no notion of users.

So basically i want Axum (rust) backend with sqlx for database connection and operations + Svelte frontend, with a static build which is _embedded_ in the rust backend, such that i can deploy this easily as a single service.

Should have a Dockerfile which allows building an image that i can use to deploy the web app.
