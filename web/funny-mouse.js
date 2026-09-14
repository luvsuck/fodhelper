/* 猫鼠游戏按钮组件
 * 用法：window.funnyMouse(按钮元素, 固定后真正触发的回调)
 * 行为：鼠标移入按钮即开始线性乱跑，需连续点中 3 次才固定，固定后点击才触发回调
 */
(function (global) {
    function funnyMouse(btn, onSuccess) {
        if (!btn) return;

        let hit = 0;        // 已点中次数
        let running = false;
        let timer = null;

        function jump() {
            const w = window.innerWidth;
            const h = window.innerHeight;
            const bw = btn.offsetWidth || 120;
            const bh = btn.offsetHeight || 44;
            const x = Math.max(8, Math.random() * (w - bw - 16));
            const y = Math.max(8, Math.random() * (h - bh - 16));
            btn.style.position = "fixed";
            btn.style.left = x + "px";
            btn.style.top = y + "px";
            btn.style.zIndex = "9999";
        }

        function start() {
            if (running || hit >= 3) return;
            running = true;
            jump();
            // 每 650ms 线性跳一次，跳完后留一小段静止窗口供用户点中
            timer = setInterval(jump, 650);
        }

        function stop() {
            running = false;
            if (timer) { clearInterval(timer); timer = null; }
            btn.style.position = "";
            btn.style.left = "";
            btn.style.top = "";
            btn.style.zIndex = "";
            btn.textContent = "生成成品库存";
        }

        // 接管按钮：移除原有 onclick，改由本组件管理点击
        btn.onclick = null;
        btn.style.transition = "left .22s linear, top .22s linear";
        btn.textContent = "🐭 生成库存";

        btn.addEventListener("mouseenter", function () {
            if (hit < 3) start();
        });

        btn.addEventListener("click", function () {
            if (hit >= 3) {
                onSuccess && onSuccess();
                return;
            }
            hit++;
            if (hit >= 3) {
                stop();
            } else {
                btn.textContent = "🐭 再点 " + (3 - hit) + " 次";
            }
        });
    }

    global.funnyMouse = funnyMouse;
})(window);
