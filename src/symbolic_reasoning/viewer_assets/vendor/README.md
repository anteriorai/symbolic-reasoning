# Bundled layout dependency

`dagre.min.js` is the unmodified browser bundle from `@dagrejs/dagre` 1.1.8,
including `@dagrejs/graphlib` 2.2.4. It is used only for positions and edge routes.
The viewer's rendering and interaction code is in `../viewer.js`.

Source: https://github.com/dagrejs/dagre/tree/v1.1.8
Archive: https://registry.npmjs.org/@dagrejs/dagre/-/dagre-1.1.8.tgz
Archive integrity (SHA-512, base64):
`5SEDlndt4W/LaVzPYJW+bSmSEZc9EzTf8rJ20WCKvjS5EAZAN0b+x0Yww7VMT4R3Wootkg+X9bUfUxazYw6Blw==`

To update, download a pinned npm archive, verify its published integrity, then
copy `dist/dagre.min.js` and the applicable licenses here. No JavaScript build
step or CDN is needed to use the Python package or open an exported replay.
