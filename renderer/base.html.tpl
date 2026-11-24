<!doctype html>
<html lang="en" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js" integrity="sha384-sG0Hv1tP1lZCk9KQmrIbY/XNwi+OY84GQqhMscbnsoBFqAz8KNCil1kvfL3Hbbk2" crossorigin="anonymous"></script>
    <style>
@@FONTS@@
      :root { --bg: @@BG@@; --accent: @@ACCENT@@; --accent2: @@ACCENT2@@; --text: @@TEXT@@; --muted: @@MUTED@@; }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { width: 1080px; height: 1920px; overflow: hidden; background: var(--bg); }
      body { font-family: "@@MONO@@", monospace; font-weight: 500; color: var(--text); }
      #root { position: relative; width: 1080px; height: 1920px; background: var(--bg); }
      .clip { position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; }
      .bgvid { object-fit: cover; }
      .scrim { background: linear-gradient(180deg, rgba(0,0,0,.55) 0%, rgba(0,0,0,.25) 45%, rgba(0,0,0,.65) 100%); }
      .bg-dark { background: var(--bg); }
      .floor-fade { background: linear-gradient(180deg, rgba(0,0,0,0) 70%, rgba(0,0,0,1) 86%); }
      .display { font-family: "@@DISPLAY@@", sans-serif; line-height: 1.14; letter-spacing: -1px; }
      .txt { position: absolute; text-align: center; text-wrap: balance; }
      .hook { color: var(--text); text-shadow: 0 4px 24px rgba(0,0,0,.6); }
      .beat { color: var(--text); text-shadow: 0 4px 24px rgba(0,0,0,.6); }
      .fact { color: var(--accent2); text-shadow: 0 4px 24px rgba(0,0,0,.6); }
      .cap { background: rgba(0,0,0,.72); padding: 18px 26px; border-radius: 14px; font-weight: 700; font-size: 48px; line-height: 1.25; color: #fff; }
      .end-icon { position: absolute; left: 400px; top: 360px; width: 280px; height: 280px; }
      .end-badge { border: 4px solid var(--accent2); color: var(--accent2); font-weight: 700; font-size: 38px; letter-spacing: 3px; height: 120px; display: flex; align-items: center; justify-content: center; }
@@CSS@@
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="@@TOTAL@@" data-width="1080" data-height="1920">
@@BODY@@
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
      const shake = (id, at, amp) => tl.fromTo(id, { x: amp }, { x: 0, duration: 0.45, ease: "elastic.out(1.2, 0.2)" }, at);
@@JS@@
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
