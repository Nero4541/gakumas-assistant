cd web-ui
npm i
npm run build
cd ../
nuitka --mingw64 --standalone --show-memory --show-progress --nofollow-import-to=tkinter --nofollow-import-to=pytouch --enable-plugin=no-qt --include-data-dir=assets=assets --include-data-dir=bin=bin --include-data-dir=model=model --include-data-dir=dist=dist --output-dir=out --linux-icon=assets/images/gakumas_logo.png --windows-icon-from-ico=assets/images/gakumas_logo.png --windows-disable-console app.py