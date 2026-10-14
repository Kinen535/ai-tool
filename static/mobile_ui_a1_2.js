(function () {
    "use strict";

    const phoneQuery =
        window.matchMedia("(max-width: 760px)");

    let themeButton = null;
    let themePlaceholder = null;

    function installThemeRelocation() {
        if (!themeButton) {
            themeButton =
                document.querySelector(
                    ".theme-toggle-button"
                );
        }

        if (!themeButton) {
            return;
        }

        if (!themePlaceholder) {
            themePlaceholder =
                document.createComment(
                    "MOBILE_UI_A1_2_THEME_HOME"
                );

            themeButton.parentNode.insertBefore(
                themePlaceholder,
                themeButton
            );
        }

        syncThemeRelocation();
    }

    function syncThemeRelocation() {
        if (!themeButton) {
            return;
        }

        if (phoneQuery.matches) {
            const sidebar =
                document.querySelector(".sidebar");

            if (!sidebar) {
                return;
            }

            if (
                themeButton.parentNode
                !== sidebar
            ) {
                sidebar.appendChild(
                    themeButton
                );
            }

            themeButton.classList.add(
                "mobile-ui-a1-sidebar-theme"
            );

            return;
        }

        themeButton.classList.remove(
            "mobile-ui-a1-sidebar-theme"
        );

        if (
            themePlaceholder
            && themePlaceholder.parentNode
        ) {
            themePlaceholder.parentNode.insertBefore(
                themeButton,
                themePlaceholder.nextSibling
            );
        }
    }


    function cellText(row, column) {
        const cells =
            row.querySelectorAll(
                "td[data-column]"
            );

        for (const cell of cells) {
            if (
                cell.dataset.column
                === column
            ) {
                return (
                    cell.textContent || ""
                ).trim();
            }
        }

        return "";
    }


    function addTextElement(
        parent,
        tag,
        className,
        text
    ) {
        const element =
            document.createElement(tag);

        element.className =
            className;

        const rawText =
            text === null
            || text === undefined
                ? ""
                : String(text).trim();

        const normalized =
            (
                rawText === ""
                || rawText === "None"
                || rawText === "none"
                || rawText === "null"
                || rawText === "undefined"
            )
                ? "—"
                : rawText;

        element.textContent =
            normalized;

        parent.appendChild(
            element
        );

        return element;
    }


    function rowIsVisible(row) {
        if (row.hidden) {
            return false;
        }

        if (
            row.style
            && row.style.display === "none"
        ) {
            return false;
        }

        return true;
    }


    function installCompareCards() {
        const root =
            document.querySelector(
                ".ca-layout"
            );

        if (!root) {
            return;
        }

        const table =
            root.querySelector(
                "[data-ca-member-table]"
            );

        const shell =
            root.querySelector(
                "[data-ca-member-table-shell]"
            );

        if (
            !table
            || !shell
            || !table.tBodies.length
        ) {
            return;
        }

        const tbody =
            table.tBodies[0];

        const switcher =
            document.createElement("div");

        switcher.className =
            "ca-mobile-view-switch";

        switcher.setAttribute(
            "aria-label",
            "成员明细显示方式"
        );

        const cardButton =
            document.createElement("button");

        cardButton.type = "button";
        cardButton.className =
            "ca-mobile-view-button";
        cardButton.textContent =
            "卡片浏览";
        cardButton.dataset.view =
            "cards";

        const tableButton =
            document.createElement("button");

        tableButton.type = "button";
        tableButton.className =
            "ca-mobile-view-button";
        tableButton.textContent =
            "完整表格";
        tableButton.dataset.view =
            "table";

        switcher.append(
            cardButton,
            tableButton
        );

        const list =
            document.createElement("div");

        list.className =
            "ca-mobile-member-list";

        list.setAttribute(
            "data-mobile-member-list",
            ""
        );

        shell.parentNode.insertBefore(
            switcher,
            shell
        );

        shell.parentNode.insertBefore(
            list,
            shell
        );


        function storedMode() {
            try {
                const value =
                    window.localStorage.getItem(
                        "compareMobileMemberViewA1"
                    );

                if (
                    value === "table"
                    || value === "cards"
                ) {
                    return value;
                }
            } catch (error) {
                /* storage can be unavailable */
            }

            return "cards";
        }


        function setMode(mode) {
            const next =
                mode === "table"
                    ? "table"
                    : "cards";

            root.dataset.mobileMemberView =
                next;

            cardButton.classList.toggle(
                "is-active",
                next === "cards"
            );

            tableButton.classList.toggle(
                "is-active",
                next === "table"
            );

            cardButton.setAttribute(
                "aria-pressed",
                next === "cards"
                    ? "true"
                    : "false"
            );

            tableButton.setAttribute(
                "aria-pressed",
                next === "table"
                    ? "true"
                    : "false"
            );

            try {
                window.localStorage.setItem(
                    "compareMobileMemberViewA1",
                    next
                );
            } catch (error) {
                /* storage can be unavailable */
            }
        }


        function createMetric(
            container,
            label,
            value
        ) {
            const box =
                document.createElement("div");

            box.className =
                "ca-mobile-metric";

            addTextElement(
                box,
                "span",
                "ca-mobile-metric-label",
                label
            );

            addTextElement(
                box,
                "strong",
                "ca-mobile-metric-value",
                value || "0"
            );

            container.appendChild(
                box
            );
        }


        const primaryColumns =
            new Set([
                "成员",
                "分组",
                "战功增长",
                "助攻增长",
                "捐献增长",
                "势力增长"
            ]);


        function createCard(row) {
            const card =
                document.createElement(
                    "article"
                );

            card.className =
                "ca-mobile-member-card";

            if (
                row.classList.contains(
                    "row-red"
                )
            ) {
                card.classList.add(
                    "is-danger"
                );
            } else if (
                row.classList.contains(
                    "row-yellow"
                )
            ) {
                card.classList.add(
                    "is-warning"
                );
            }

            const head =
                document.createElement(
                    "div"
                );

            head.className =
                "ca-mobile-member-head";

            const identity =
                document.createElement(
                    "div"
                );

            identity.style.minWidth =
                "0";

            addTextElement(
                identity,
                "div",
                "ca-mobile-member-name",
                cellText(row, "成员")
            );

            addTextElement(
                identity,
                "div",
                "ca-mobile-member-group",
                cellText(row, "分组")
                    || "未分组"
            );

            head.appendChild(
                identity
            );

            const status =
                (
                    cellText(
                        row,
                        "综合考勤状态"
                    )
                    || cellText(
                        row,
                        "状态"
                    )
                    || row.dataset.type
                    || "正常"
                );

            addTextElement(
                head,
                "span",
                "ca-mobile-member-status",
                status
            );

            card.appendChild(
                head
            );

            const metrics =
                document.createElement(
                    "div"
                );

            metrics.className =
                "ca-mobile-member-metrics";

            createMetric(
                metrics,
                "战功增长",
                cellText(
                    row,
                    "战功增长"
                )
            );

            createMetric(
                metrics,
                "助攻增长",
                cellText(
                    row,
                    "助攻增长"
                )
            );

            createMetric(
                metrics,
                "捐献增长",
                cellText(
                    row,
                    "捐献增长"
                )
            );

            createMetric(
                metrics,
                "势力增长",
                cellText(
                    row,
                    "势力增长"
                )
            );

            card.appendChild(
                metrics
            );

            const details =
                document.createElement(
                    "details"
                );

            details.className =
                "ca-mobile-member-details";

            const summary =
                document.createElement(
                    "summary"
                );

            summary.textContent =
                "展开完整指标";

            details.appendChild(
                summary
            );

            const detailGrid =
                document.createElement(
                    "div"
                );

            detailGrid.className =
                "ca-mobile-detail-grid";

            const cells =
                row.querySelectorAll(
                    "td[data-column]"
                );

            for (const cell of cells) {
                const column =
                    cell.dataset.column || "";

                if (
                    !column
                    || primaryColumns.has(
                        column
                    )
                ) {
                    continue;
                }

                const detailRow =
                    document.createElement(
                        "div"
                    );

                detailRow.className =
                    "ca-mobile-detail-row";

                addTextElement(
                    detailRow,
                    "span",
                    "ca-mobile-detail-label",
                    column
                );

                addTextElement(
                    detailRow,
                    "span",
                    "ca-mobile-detail-value",
                    (
                        cell.textContent
                        || "-"
                    ).trim()
                );

                detailGrid.appendChild(
                    detailRow
                );
            }

            details.appendChild(
                detailGrid
            );

            card.appendChild(
                details
            );

            return card;
        }


        let refreshTimer = null;

        function refreshCards() {
            if (!phoneQuery.matches) {
                return;
            }

            list.replaceChildren();

            const rows =
                Array.from(
                    tbody.rows
                ).filter(
                    rowIsVisible
                );

            if (!rows.length) {
                const empty =
                    document.createElement(
                        "div"
                    );

                empty.className =
                    "ca-mobile-empty";

                empty.textContent =
                    "当前筛选条件下没有成员记录。";

                list.appendChild(
                    empty
                );

                return;
            }

            for (const row of rows) {
                list.appendChild(
                    createCard(row)
                );
            }
        }


        function scheduleRefresh() {
            if (refreshTimer) {
                window.clearTimeout(
                    refreshTimer
                );
            }

            refreshTimer =
                window.setTimeout(
                    refreshCards,
                    40
                );
        }


        cardButton.addEventListener(
            "click",
            function () {
                setMode("cards");
                scheduleRefresh();
            }
        );

        tableButton.addEventListener(
            "click",
            function () {
                setMode("table");
            }
        );


        root.addEventListener(
            "input",
            scheduleRefresh
        );

        root.addEventListener(
            "change",
            scheduleRefresh
        );

        root.addEventListener(
            "click",
            function (event) {
                const target =
                    event.target;

                if (
                    target instanceof Element
                    && target.closest(
                        ".ca-mobile-member-card, "
                        + ".ca-mobile-view-switch"
                    )
                ) {
                    return;
                }

                window.setTimeout(
                    scheduleRefresh,
                    80
                );
            }
        );


        const observer =
            new MutationObserver(
                scheduleRefresh
            );

        observer.observe(
            tbody,
            {
                childList: true,
                attributes: true,
                subtree: false,
                attributeFilter: [
                    "class",
                    "style",
                    "hidden"
                ]
            }
        );


        function syncPhoneMode() {
            if (phoneQuery.matches) {
                setMode(
                    root.dataset.mobileMemberView
                    || storedMode()
                );

                scheduleRefresh();
            }
        }

        if (
            typeof phoneQuery.addEventListener
            === "function"
        ) {
            phoneQuery.addEventListener(
                "change",
                syncPhoneMode
            );
        } else if (
            typeof phoneQuery.addListener
            === "function"
        ) {
            phoneQuery.addListener(
                syncPhoneMode
            );
        }

        setMode(
            storedMode()
        );

        refreshCards();
    }


    function initialise() {
        installThemeRelocation();
        installCompareCards();
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initialise
        );
    } else {
        initialise();
    }


    if (
        typeof phoneQuery.addEventListener
        === "function"
    ) {
        phoneQuery.addEventListener(
            "change",
            syncThemeRelocation
        );
    } else if (
        typeof phoneQuery.addListener
        === "function"
    ) {
        phoneQuery.addListener(
            syncThemeRelocation
        );
    }
})();

/*
============================================================
MOBILE_UI_A1_3_TRENDS
============================================================
*/

(function () {
    "use strict";

    const phoneQuery =
        window.matchMedia(
            "(max-width: 760px)"
        );


    function normaliseText(value) {
        const raw =
            value === null
            || value === undefined
                ? ""
                : String(value).trim();

        if (
            raw === ""
            || raw === "None"
            || raw === "none"
            || raw === "null"
            || raw === "undefined"
        ) {
            return "—";
        }

        return raw;
    }


    function addText(
        parent,
        tag,
        className,
        value
    ) {
        const element =
            document.createElement(tag);

        element.className =
            className;

        element.textContent =
            normaliseText(value);

        parent.appendChild(
            element
        );

        return element;
    }


    function tableHeaders(table) {
        const headers = [];

        const cells =
            table.querySelectorAll(
                "thead th"
            );

        cells.forEach(
            (cell, index) => {
                headers.push(
                    normaliseText(
                        cell.textContent
                    )
                    || ("字段 " + (index + 1))
                );
            }
        );

        return headers;
    }


    function rowValues(row) {
        return Array.from(
            row.querySelectorAll("td")
        ).map(
            cell => normaliseText(
                cell.textContent
            )
        );
    }


    function headerIndex(
        headers,
        candidates
    ) {
        for (
            let i = 0;
            i < headers.length;
            i += 1
        ) {
            const header =
                headers[i];

            for (
                const candidate
                of candidates
            ) {
                if (
                    header.includes(
                        candidate
                    )
                ) {
                    return i;
                }
            }
        }

        return -1;
    }


    function metric(
        container,
        label,
        value
    ) {
        const box =
            document.createElement(
                "div"
            );

        box.className =
            "trends-mobile-metric";

        addText(
            box,
            "span",
            "trends-mobile-metric-label",
            label
        );

        addText(
            box,
            "strong",
            "trends-mobile-metric-value",
            value
        );

        container.appendChild(
            box
        );
    }


    function createCard(
        headers,
        values,
        isMemberHistory
    ) {
        const card =
            document.createElement(
                "article"
            );

        card.className =
            "trends-mobile-card";

        const head =
            document.createElement(
                "div"
            );

        head.className =
            "trends-mobile-card-head";

        const identity =
            document.createElement(
                "div"
            );

        identity.style.minWidth =
            "0";


        let title = values[0] || "历史记录";
        let subtitle = "";
        let badge = "";


        if (isMemberHistory) {
            const memberIndex =
                headerIndex(
                    headers,
                    ["成员"]
                );

            const timeIndex =
                headerIndex(
                    headers,
                    ["时间点", "时间"]
                );

            const groupIndex =
                headerIndex(
                    headers,
                    ["所属团", "分组"]
                );

            if (
                memberIndex >= 0
                && values[memberIndex]
            ) {
                title =
                    values[memberIndex];
            }

            const parts = [];

            if (
                timeIndex >= 0
                && values[timeIndex]
            ) {
                parts.push(
                    values[timeIndex]
                );
            }

            if (
                groupIndex >= 0
                && values[groupIndex]
            ) {
                parts.push(
                    values[groupIndex]
                );
            }

            subtitle =
                parts.join(" · ");

        } else {

            const qualityIndex =
                headerIndex(
                    headers,
                    ["质量"]
                );

            title =
                "区间 " +
                normaliseText(
                    values[0]
                );

            if (qualityIndex >= 0) {
                badge =
                    values[
                        qualityIndex
                    ];
            }
        }


        addText(
            identity,
            "div",
            "trends-mobile-card-title",
            title
        );

        if (subtitle) {
            addText(
                identity,
                "div",
                "trends-mobile-card-subtitle",
                subtitle
            );
        }

        head.appendChild(
            identity
        );

        if (badge) {
            addText(
                head,
                "span",
                "trends-mobile-card-badge",
                badge
            );
        }

        card.appendChild(
            head
        );


        const metrics =
            document.createElement(
                "div"
            );

        metrics.className =
            "trends-mobile-metrics";


        const wanted =
            isMemberHistory
                ? [
                    "战功总量",
                    "助攻总量",
                    "势力值"
                ]
                : [
                    "成员覆盖",
                    "战功",
                    "助攻",
                    "捐献",
                    "势力"
                ];


        let added = 0;

        for (const wantedLabel of wanted) {
            const index =
                headerIndex(
                    headers,
                    [wantedLabel]
                );

            if (
                index < 0
                || index >= values.length
            ) {
                continue;
            }

            metric(
                metrics,
                headers[index],
                values[index]
            );

            added += 1;

            if (added >= 4) {
                break;
            }
        }


        if (added === 0) {
            for (
                let i = 1;
                i < Math.min(
                    headers.length,
                    values.length,
                    5
                );
                i += 1
            ) {
                metric(
                    metrics,
                    headers[i],
                    values[i]
                );
            }
        }

        card.appendChild(
            metrics
        );


        const details =
            document.createElement(
                "details"
            );

        details.className =
            "trends-mobile-details";

        const summary =
            document.createElement(
                "summary"
            );

        summary.textContent =
            "查看完整记录";

        details.appendChild(
            summary
        );


        const detailBody =
            document.createElement(
                "div"
            );

        for (
            let i = 0;
            i < Math.min(
                headers.length,
                values.length
            );
            i += 1
        ) {
            const line =
                document.createElement(
                    "div"
                );

            line.className =
                "trends-mobile-detail-row";

            addText(
                line,
                "span",
                "trends-mobile-detail-label",
                headers[i]
            );

            addText(
                line,
                "span",
                "trends-mobile-detail-value",
                values[i]
            );

            detailBody.appendChild(
                line
            );
        }

        details.appendChild(
            detailBody
        );

        card.appendChild(
            details
        );

        return card;
    }


    function installHistorySection(
        container,
        sectionIndex
    ) {
        if (
            container.dataset
                .mobileHistoryInstalled
            === "1"
        ) {
            return;
        }

        const table =
            container.querySelector(
                ":scope > table"
            );

        if (!table) {
            return;
        }

        const tbody =
            table.tBodies[0];

        if (!tbody) {
            return;
        }

        container.dataset
            .mobileHistoryInstalled =
            "1";


        const label =
            (
                container.getAttribute(
                    "aria-label"
                )
                || ""
            );

        const isMemberHistory =
            label.includes(
                "成员完整历史"
            );


        const switcher =
            document.createElement(
                "div"
            );

        switcher.className =
            "trends-mobile-view-switch";


        const cardsButton =
            document.createElement(
                "button"
            );

        cardsButton.type =
            "button";

        cardsButton.className =
            "trends-mobile-view-button";

        cardsButton.textContent =
            "卡片浏览";


        const tableButton =
            document.createElement(
                "button"
            );

        tableButton.type =
            "button";

        tableButton.className =
            "trends-mobile-view-button";

        tableButton.textContent =
            "完整表格";


        switcher.append(
            cardsButton,
            tableButton
        );


        const list =
            document.createElement(
                "div"
            );

        list.className =
            "trends-mobile-card-list";


        const headers =
            tableHeaders(table);

        const rows =
            Array.from(
                tbody.rows
            );


        const batchSize = 12;
        let visibleCount = 0;

        const footer =
            document.createElement(
                "div"
            );

        footer.className =
            "trends-mobile-batch-footer";

        const counter =
            document.createElement(
                "div"
            );

        counter.className =
            "trends-mobile-batch-counter";

        const loadMore =
            document.createElement(
                "button"
            );

        loadMore.type = "button";
        loadMore.className =
            "trends-mobile-load-more";
        loadMore.textContent =
            "加载更多 12 条";

        footer.append(
            counter,
            loadMore
        );


        function renderNextBatch() {
            const next =
                Math.min(
                    visibleCount + batchSize,
                    rows.length
                );

            for (
                let i = visibleCount;
                i < next;
                i += 1
            ) {
                list.appendChild(
                    createCard(
                        headers,
                        rowValues(rows[i]),
                        isMemberHistory
                    )
                );
            }

            visibleCount = next;

            counter.textContent =
                "已显示 "
                + visibleCount
                + " / "
                + rows.length;

            if (
                visibleCount >= rows.length
            ) {
                loadMore.hidden = true;
            }
        }


        loadMore.addEventListener(
            "click",
            renderNextBatch
        );


        renderNextBatch();

        list.appendChild(
            footer
        );


        container.parentNode.insertBefore(
            switcher,
            container
        );

        container.insertBefore(
            list,
            table
        );


        const storageKey =
            (
                "trendsMobileHistoryViewA1_"
                + sectionIndex
            );


        function readMode() {
            try {
                const value =
                    window.localStorage
                        .getItem(
                            storageKey
                        );

                if (
                    value === "cards"
                    || value === "table"
                ) {
                    return value;
                }
            } catch (error) {
                /* unavailable storage */
            }

            return "cards";
        }


        function setMode(mode) {
            const next =
                mode === "table"
                    ? "table"
                    : "cards";

            container.dataset
                .mobileHistoryView =
                next;

            cardsButton.classList
                .toggle(
                    "is-active",
                    next === "cards"
                );

            tableButton.classList
                .toggle(
                    "is-active",
                    next === "table"
                );

            cardsButton.setAttribute(
                "aria-pressed",
                next === "cards"
                    ? "true"
                    : "false"
            );

            tableButton.setAttribute(
                "aria-pressed",
                next === "table"
                    ? "true"
                    : "false"
            );

            try {
                window.localStorage
                    .setItem(
                        storageKey,
                        next
                    );
            } catch (error) {
                /* unavailable storage */
            }
        }


        cardsButton.addEventListener(
            "click",
            () => setMode("cards")
        );

        tableButton.addEventListener(
            "click",
            () => setMode("table")
        );

        setMode(
            readMode()
        );
    }


    function installTrendsMobile() {
        const page =
            document.getElementById(
                "trends-evidence-page"
            );

        if (!page) {
            return;
        }


        const sections =
            page.querySelectorAll(
                ".trends-history-scroll"
            );

        sections.forEach(
            (container, index) => {
                installHistorySection(
                    container,
                    index
                );
            }
        );


        if (phoneQuery.matches) {
            page
                .querySelectorAll(
                    ".trends-history-note"
                )
                .forEach(
                    note => {
                        const text =
                            note.textContent
                            || "";

                        if (
                            text.includes(
                                "在表格内滚动查看完整历史"
                            )
                        ) {
                            note.textContent =
                                text.replace(
                                    "在表格内滚动查看完整历史",
                                    "手机默认卡片浏览，可切换完整表格"
                                );
                        }
                    }
                );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            installTrendsMobile
        );
    } else {
        installTrendsMobile();
    }
})();

/*
============================================================
MOBILE_UI_A1_4_R1_REPUTATION
============================================================
*/

(function () {
    "use strict";


    function actionPath(form) {
        if (!form) {
            return "";
        }

        const raw =
            form.getAttribute(
                "action"
            ) || "";

        try {
            return new URL(
                raw,
                window.location.origin
            ).pathname;
        } catch (error) {
            return raw;
        }
    }


    function markFlowNavigation(root) {
        const labels = new Set([
            "录入首页",
            "档案管理",
            "事件记录",
            "风险处理",
            "检索资料"
        ]);

        const candidates =
            root.querySelectorAll(
                "nav, header, "
                + ".rf-nav, "
                + ".rf-flow-nav, "
                + "div"
            );

        for (const candidate of candidates) {
            const directLinks =
                Array.from(
                    candidate.children
                ).filter(
                    child =>
                        child.tagName === "A"
                );

            if (
                directLinks.length < 3
            ) {
                continue;
            }

            let matches = 0;

            for (const link of directLinks) {
                const text =
                    (
                        link.textContent
                        || ""
                    ).trim();

                if (labels.has(text)) {
                    matches += 1;
                }
            }

            if (matches >= 3) {
                candidate.classList.add(
                    "mobile-reputation-nav"
                );

                return;
            }
        }
    }


    function markForms(root) {
        root.querySelectorAll(
            "form"
        ).forEach(
            form => {
                const path =
                    actionPath(form);

                if (
                    path
                    === "/reputation/search"
                ) {
                    form.classList.add(
                        "mobile-reputation-search-form"
                    );
                }

                if (
                    path
                    === "/reputation/quick-link"
                ) {
                    form.classList.add(
                        "mobile-reputation-quick-link"
                    );
                }

                if (
                    path
                    === "/reputation/tasks"
                ) {
                    form.classList.add(
                        "mobile-reputation-filter-form"
                    );
                }
            }
        );
    }


    function markInlineGrids(root) {
        root.querySelectorAll(
            "[style]"
        ).forEach(
            element => {
                const style =
                    (
                        element.getAttribute(
                            "style"
                        )
                        || ""
                    )
                    .replace(
                        /\s+/g,
                        ""
                    )
                    .toLowerCase();

                if (
                    !style.includes(
                        "grid-template-columns:"
                    )
                ) {
                    return;
                }


                /*
                   Desktop master/detail and split layouts.
                */

                if (
                    style.includes(
                        "grid-template-columns:0.95fr1.25fr"
                    )
                    ||
                    style.includes(
                        "grid-template-columns:0.85fr1.15fr"
                    )
                    ||
                    style.includes(
                        "grid-template-columns:0.35fr0.65fr"
                    )
                ) {
                    element.classList.add(
                        "mobile-reputation-stack-grid"
                    );

                    return;
                }


                /*
                   3–9 column metric strips.
                */

                if (
                    /grid-template-columns:repeat\([3-9],/.test(
                        style
                    )
                ) {
                    element.classList.add(
                        "mobile-reputation-stat-grid"
                    );
                }
            }
        );
    }


    function markTables(root) {
        root.querySelectorAll(
            "table"
        ).forEach(
            table => {
                if (
                    table.closest(
                        ".rf-table-wrap, "
                        + ".reputation-task-table-card, "
                        + ".reputation-workbench-table-card, "
                        + ".rep-import-table-wrap"
                    )
                ) {
                    return;
                }

                const parent =
                    table.parentElement;

                if (parent) {
                    parent.classList.add(
                        "mobile-reputation-table-wrap"
                    );
                }
            }
        );
    }


    function installReputationMobile() {
        const roots =
            Array.from(
                document.querySelectorAll(
                    ".rf-flow, "
                    + ".rf-legacy-shell, "
                    + ".reputation-task-page, "
                    + ".reputation-workbench"
                )
            );

        if (!roots.length) {
            return;
        }

        for (const root of roots) {
            if (
                root.dataset
                    .mobileReputationA14
                === "1"
            ) {
                continue;
            }

            root.dataset
                .mobileReputationA14 =
                "1";

            markFlowNavigation(
                root
            );

            markForms(
                root
            );

            markInlineGrids(
                root
            );

            markTables(
                root
            );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            installReputationMobile
        );
    } else {
        installReputationMobile();
    }
})();

/*
============================================================
MOBILE_UI_A1_4_R2_MEMBERS
============================================================
*/

(function () {
    "use strict";

    const phoneQuery =
        window.matchMedia(
            "(max-width: 760px)"
        );


    function clean(value) {
        const raw =
            value === null
            || value === undefined
                ? ""
                : String(value)
                    .replace(
                        /\s+/g,
                        " "
                    )
                    .trim();

        if (
            raw === ""
            || raw === "None"
            || raw === "none"
            || raw === "null"
            || raw === "undefined"
        ) {
            return "—";
        }

        return raw;
    }


    function cleanHeader(value) {
        return clean(value)
            .replace(
                /[↕↑↓▲▼]/g,
                ""
            )
            .replace(
                /\s+/g,
                " "
            )
            .trim();
    }


    function addText(
        parent,
        tag,
        className,
        value
    ) {
        const element =
            document.createElement(
                tag
            );

        element.className =
            className;

        element.textContent =
            clean(value);

        parent.appendChild(
            element
        );

        return element;
    }


    function findHeader(
        headers,
        candidates
    ) {
        for (
            let i = 0;
            i < headers.length;
            i += 1
        ) {
            const header =
                headers[i];

            for (
                const candidate
                of candidates
            ) {
                if (
                    header.includes(
                        candidate
                    )
                ) {
                    return i;
                }
            }
        }

        return -1;
    }


    function installMembersMobile() {
        const table =
            document.getElementById(
                "memberManagementTable"
            );

        const scroll =
            document.getElementById(
                "memberManagementTableScroll"
            );

        if (
            !table
            || !scroll
            || !table.tBodies.length
        ) {
            return;
        }

        if (
            table.dataset
                .mobileMembersInstalled
            === "1"
        ) {
            return;
        }

        table.dataset
            .mobileMembersInstalled =
            "1";


        const host =
            scroll.parentElement;

        if (!host) {
            return;
        }

        host.classList.add(
            "mobile-members-a1-host"
        );


        const headers =
            Array.from(
                table.querySelectorAll(
                    "thead th"
                )
            ).map(
                th =>
                    cleanHeader(
                        th.textContent
                    )
            );


        const allRows =
            Array.from(
                table.querySelectorAll(
                    "tbody tr[data-member-row]"
                )
            );


        /*
           Mobile toolbar
        */

        const toolbar =
            document.createElement(
                "div"
            );

        toolbar.className =
            "mobile-members-toolbar";


        const search =
            document.createElement(
                "input"
            );

        search.type =
            "search";

        search.className =
            "mobile-members-search";

        search.placeholder =
            "搜索成员 / 分组 / 州";

        search.autocomplete =
            "off";

        search.setAttribute(
            "aria-label",
            "搜索成员"
        );


        const switcher =
            document.createElement(
                "div"
            );

        switcher.className =
            "mobile-members-view-switch";


        const cardsButton =
            document.createElement(
                "button"
            );

        cardsButton.type =
            "button";

        cardsButton.className =
            "mobile-members-view-button";

        cardsButton.textContent =
            "卡片浏览";


        const tableButton =
            document.createElement(
                "button"
            );

        tableButton.type =
            "button";

        tableButton.className =
            "mobile-members-view-button";

        tableButton.textContent =
            "完整表格";


        switcher.append(
            cardsButton,
            tableButton
        );

        toolbar.append(
            search,
            switcher
        );


        const list =
            document.createElement(
                "div"
            );

        list.className =
            "mobile-members-card-list";


        host.insertBefore(
            toolbar,
            scroll
        );

        host.insertBefore(
            list,
            scroll
        );


        /*
           Header indices
        */

        const memberIndex =
            findHeader(
                headers,
                ["成员", "昵称"]
            );

        const groupIndex =
            findHeader(
                headers,
                ["分组", "所属团"]
            );

        const stateIndex =
            findHeader(
                headers,
                [
                    "状态",
                    "风险",
                    "趋势",
                    "标签"
                ]
            );

        const regionIndex =
            findHeader(
                headers,
                ["所属州", "州"]
            );


        const metricDefinitions = [
            {
                label: "势力值",
                candidates: [
                    "势力值"
                ]
            },
            {
                label: "战功总量",
                candidates: [
                    "战功总量"
                ]
            },
            {
                label: "助攻总量",
                candidates: [
                    "助攻总量"
                ]
            },
            {
                label: "捐献总量",
                candidates: [
                    "捐献总量",
                    "贡献总量"
                ]
            }
        ];


        const primaryIndices =
            new Set([
                memberIndex,
                groupIndex,
                stateIndex,
                regionIndex
            ]);


        const resolvedMetrics =
            metricDefinitions.map(
                definition => {
                    const index =
                        findHeader(
                            headers,
                            definition.candidates
                        );

                    if (index >= 0) {
                        primaryIndices.add(
                            index
                        );
                    }

                    return {
                        label:
                            definition.label,
                        index:
                            index
                    };
                }
            );


        function valuesFor(row) {
            return Array.from(
                row.cells
            ).map(
                cell =>
                    clean(
                        cell.textContent
                    )
            );
        }


        function metric(
            container,
            label,
            value
        ) {
            const box =
                document.createElement(
                    "div"
                );

            box.className =
                "mobile-member-metric";

            addText(
                box,
                "span",
                "mobile-member-metric-label",
                label
            );

            addText(
                box,
                "strong",
                "mobile-member-metric-value",
                value
            );

            container.appendChild(
                box
            );
        }


        function createCard(row) {
            const values =
                valuesFor(row);

            const card =
                document.createElement(
                    "article"
                );

            card.className =
                "mobile-member-card";


            const head =
                document.createElement(
                    "div"
                );

            head.className =
                "mobile-member-card-head";


            const identity =
                document.createElement(
                    "div"
                );

            identity.style.minWidth =
                "0";


            const member =
                memberIndex >= 0
                    ? values[
                        memberIndex
                    ]
                    : values[0];


            addText(
                identity,
                "div",
                "mobile-member-name",
                member
            );


            const subtitleParts = [];

            if (
                groupIndex >= 0
                && values[groupIndex]
                !== "—"
            ) {
                subtitleParts.push(
                    values[groupIndex]
                );
            }

            if (
                regionIndex >= 0
                && values[regionIndex]
                !== "—"
            ) {
                subtitleParts.push(
                    values[regionIndex]
                );
            }


            if (
                subtitleParts.length
            ) {
                addText(
                    identity,
                    "div",
                    "mobile-member-subtitle",
                    subtitleParts.join(
                        " · "
                    )
                );
            }

            head.appendChild(
                identity
            );


            if (
                stateIndex >= 0
                && values[stateIndex]
                !== "—"
            ) {
                addText(
                    head,
                    "span",
                    "mobile-member-badge",
                    values[stateIndex]
                );
            }

            card.appendChild(
                head
            );


            const metrics =
                document.createElement(
                    "div"
                );

            metrics.className =
                "mobile-member-metrics";


            let metricCount = 0;

            for (
                const definition
                of resolvedMetrics
            ) {
                if (
                    definition.index < 0
                ) {
                    continue;
                }

                metric(
                    metrics,
                    definition.label,
                    values[
                        definition.index
                    ]
                );

                metricCount += 1;
            }


            /*
               Safety fallback if current
               schema lacks one of the
               expected metrics.
            */

            if (metricCount < 2) {
                for (
                    let i = 0;
                    i < headers.length;
                    i += 1
                ) {
                    if (
                        primaryIndices.has(i)
                    ) {
                        continue;
                    }

                    metric(
                        metrics,
                        headers[i],
                        values[i]
                    );

                    metricCount += 1;

                    if (
                        metricCount >= 4
                    ) {
                        break;
                    }
                }
            }

            card.appendChild(
                metrics
            );


            /*
               Complete record
            */

            const details =
                document.createElement(
                    "div"
                );

            details.className =
                "mobile-member-details";


            const toggle =
                document.createElement(
                    "button"
                );

            toggle.type =
                "button";

            toggle.className =
                "mobile-member-details-toggle";

            toggle.textContent =
                "展开完整资料 ↓";

            toggle.setAttribute(
                "aria-expanded",
                "false"
            );


            const detailBody =
                document.createElement(
                    "div"
                );

            detailBody.className =
                "mobile-member-details-body";

            detailBody.hidden = true;


            /*
               Full record means FULL record.
               Do not exclude fields already
               shown in the compact card.
            */
            for (
                let i = 0;
                i < Math.min(
                    headers.length,
                    values.length
                );
                i += 1
            ) {
                const rowElement =
                    document.createElement(
                        "div"
                    );

                rowElement.className =
                    "mobile-member-detail-row";

                addText(
                    rowElement,
                    "span",
                    "mobile-member-detail-label",
                    headers[i]
                        || (
                            "字段 "
                            + (i + 1)
                        )
                );

                addText(
                    rowElement,
                    "span",
                    "mobile-member-detail-value",
                    values[i]
                );

                detailBody.appendChild(
                    rowElement
                );
            }


            toggle.addEventListener(
                "click",
                function (event) {
                    event.preventDefault();
                    event.stopPropagation();

                    const expanded =
                        toggle.getAttribute(
                            "aria-expanded"
                        ) === "true";

                    const next =
                        !expanded;

                    toggle.setAttribute(
                        "aria-expanded",
                        next
                            ? "true"
                            : "false"
                    );

                    detailBody.hidden =
                        !next;

                    toggle.textContent =
                        next
                            ? "收起完整资料 ↑"
                            : "展开完整资料 ↓";
                }
            );


            if (
                detailBody.children.length === 0
            ) {
                const empty =
                    document.createElement(
                        "div"
                    );

                empty.className =
                    "mobile-member-detail-row";

                addText(
                    empty,
                    "span",
                    "mobile-member-detail-label",
                    "资料"
                );

                addText(
                    empty,
                    "span",
                    "mobile-member-detail-value",
                    "当前记录暂无更多字段"
                );

                detailBody.appendChild(
                    empty
                );
            }

            details.append(
                toggle,
                detailBody
            );

            card.appendChild(
                details
            );

            return card;
        }


        /*
           Filtering + batching
        */

        const batchSize = 15;

        let visibleCount = 0;
        let filteredRows = [];


        const footer =
            document.createElement(
                "div"
            );

        footer.className =
            "mobile-members-batch-footer";


        const counter =
            document.createElement(
                "div"
            );

        counter.className =
            "mobile-members-batch-counter";


        const loadMore =
            document.createElement(
                "button"
            );

        loadMore.type =
            "button";

        loadMore.className =
            "mobile-members-load-more";

        loadMore.textContent =
            "加载更多 15 条";


        footer.append(
            counter,
            loadMore
        );


        function matchingRows() {
            const query =
                (
                    search.value
                    || ""
                )
                .trim()
                .toLowerCase();

            if (!query) {
                return Array.from(
                    table.querySelectorAll(
                        "tbody tr[data-member-row]"
                    )
                );
            }

            return Array.from(
                table.querySelectorAll(
                    "tbody tr[data-member-row]"
                )
            ).filter(
                row =>
                    (
                        row.textContent
                        || ""
                    )
                    .toLowerCase()
                    .includes(query)
            );
        }


        function updateCounter() {
            counter.textContent =
                "已显示 "
                + visibleCount
                + " / "
                + filteredRows.length;

            loadMore.hidden =
                visibleCount
                >= filteredRows.length;
        }


        function appendBatch() {
            const next =
                Math.min(
                    visibleCount
                    + batchSize,
                    filteredRows.length
                );

            for (
                let i = visibleCount;
                i < next;
                i += 1
            ) {
                list.insertBefore(
                    createCard(
                        filteredRows[i]
                    ),
                    footer
                );
            }

            visibleCount =
                next;

            updateCounter();
        }


        function rebuildCards() {
            list.replaceChildren();

            filteredRows =
                matchingRows();

            visibleCount = 0;

            list.appendChild(
                footer
            );

            if (
                filteredRows.length === 0
            ) {
                counter.textContent =
                    "没有找到匹配成员";

                loadMore.hidden =
                    true;

                return;
            }

            appendBatch();
        }


        loadMore.addEventListener(
            "click",
            appendBatch
        );


        let searchTimer = null;

        search.addEventListener(
            "input",
            function () {
                if (searchTimer) {
                    window.clearTimeout(
                        searchTimer
                    );
                }

                searchTimer =
                    window.setTimeout(
                        rebuildCards,
                        80
                    );
            }
        );


        /*
           View switching
        */

        const storageKey =
            "membersMobileViewA1";


        function readMode() {
            try {
                const value =
                    window.localStorage
                        .getItem(
                            storageKey
                        );

                if (
                    value === "cards"
                    || value === "table"
                ) {
                    return value;
                }
            } catch (error) {
                /* no storage */
            }

            return "cards";
        }


        function setMode(mode) {
            const next =
                mode === "table"
                    ? "table"
                    : "cards";

            host.dataset
                .mobileMemberView =
                next;

            cardsButton.classList.toggle(
                "is-active",
                next === "cards"
            );

            tableButton.classList.toggle(
                "is-active",
                next === "table"
            );

            cardsButton.setAttribute(
                "aria-pressed",
                next === "cards"
                    ? "true"
                    : "false"
            );

            tableButton.setAttribute(
                "aria-pressed",
                next === "table"
                    ? "true"
                    : "false"
            );

            try {
                window.localStorage
                    .setItem(
                        storageKey,
                        next
                    );
            } catch (error) {
                /* no storage */
            }

            if (
                next === "cards"
                && phoneQuery.matches
            ) {
                rebuildCards();
            }
        }


        cardsButton.addEventListener(
            "click",
            () => setMode("cards")
        );

        tableButton.addEventListener(
            "click",
            () => setMode("table")
        );


        /*
           If desktop table sorting changes
           tbody order, card mode rebuilds
           from the actual new row order
           when the user returns.
        */

        function syncViewport() {
            if (phoneQuery.matches) {
                setMode(
                    host.dataset
                        .mobileMemberView
                    || readMode()
                );
            }
        }


        if (
            typeof phoneQuery
                .addEventListener
            === "function"
        ) {
            phoneQuery.addEventListener(
                "change",
                syncViewport
            );
        } else if (
            typeof phoneQuery
                .addListener
            === "function"
        ) {
            phoneQuery.addListener(
                syncViewport
            );
        }


        setMode(
            readMode()
        );

        if (
            phoneQuery.matches
        ) {
            rebuildCards();
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            installMembersMobile
        );
    } else {
        installMembersMobile();
    }
})();

/* MOBILE_UI_A1_4_R2_R2_MEMBER_DETAILS_CONTENT_FIX */

/*
============================================================
MOBILE_UI_A1_5_R1_TABLET_PORTRAIT
============================================================
*/

(function () {
    "use strict";

    const tabletQuery =
        window.matchMedia(
            "(min-width: 761px) "
            + "and (max-width: 1100px) "
            + "and (orientation: portrait)"
        );


    function normaliseGrid(value) {
        return (
            value || ""
        )
        .replace(
            /\s+/g,
            ""
        )
        .toLowerCase();
    }


    function wrapTable(table) {
        if (!table) {
            return;
        }

        if (
            table.closest(
                ".tablet-a15-table-scroll"
            )
        ) {
            return;
        }

        const parent =
            table.parentNode;

        if (!parent) {
            return;
        }

        const wrapper =
            document.createElement(
                "div"
            );

        wrapper.className =
            "tablet-a15-table-scroll";

        parent.insertBefore(
            wrapper,
            table
        );

        wrapper.appendChild(
            table
        );
    }


    function markTasks(root) {
        root.querySelectorAll(
            "[style]"
        ).forEach(
            element => {
                const grid =
                    normaliseGrid(
                        element.style
                            .gridTemplateColumns
                    );

                if (!grid) {
                    return;
                }

                if (
                    element.id
                    === "taskFilterForm"
                ) {
                    element.classList.add(
                        "tablet-task-filter-grid"
                    );

                    return;
                }

                if (
                    grid
                    === "repeat(8,1fr)"
                ) {
                    element.classList.add(
                        "tablet-task-stats-8"
                    );

                    return;
                }

                if (
                    grid
                    === "repeat(6,1fr)"
                ) {
                    element.classList.add(
                        "tablet-task-stats-6"
                    );

                    return;
                }

                if (
                    grid === "1.4fr1fr"
                    ||
                    grid === "1.3fr1fr"
                ) {
                    element.classList.add(
                        "tablet-task-split"
                    );
                }
            }
        );


        root.querySelectorAll(
            "table.task-table"
        ).forEach(
            wrapTable
        );
    }


    function markStrategic(root) {
        root.querySelectorAll(
            "[style]"
        ).forEach(
            element => {
                const grid =
                    normaliseGrid(
                        element.style
                            .gridTemplateColumns
                    );

                if (!grid) {
                    return;
                }

                if (
                    grid
                    === "repeat(6,1fr)"
                ) {
                    element.classList.add(
                        "tablet-strategic-grid-6"
                    );

                    return;
                }

                if (
                    grid
                    === "repeat(5,1fr)"
                ) {
                    element.classList.add(
                        "tablet-strategic-grid-5"
                    );

                    return;
                }

                if (
                    grid
                    === "repeat(4,1fr)"
                ) {
                    element.classList.add(
                        "tablet-strategic-grid-4"
                    );

                    return;
                }

                if (
                    grid
                    === "repeat(3,1fr)"
                ) {
                    element.classList.add(
                        "tablet-strategic-grid-3"
                    );

                    return;
                }

                if (
                    grid === "1fr1fr"
                    ||
                    grid === "1.4fr1fr"
                ) {
                    element.classList.add(
                        "tablet-strategic-split"
                    );
                }
            }
        );
    }


    function markSnapshots(root) {
        root.querySelectorAll(
            "table"
        ).forEach(
            wrapTable
        );
    }


    function ensureThemeProxy(
        sidebar
    ) {
        const original =
            document.querySelector(
                ".theme-toggle-button"
            );

        if (!original) {
            return;
        }

        original.classList.add(
            "tablet-a15-theme-original"
        );

        let proxy =
            sidebar.querySelector(
                ".tablet-a15-theme-proxy"
            );

        if (!proxy) {
            proxy =
                document.createElement(
                    "button"
                );

            proxy.type =
                "button";

            proxy.className =
                "tablet-a15-theme-proxy";

            proxy.addEventListener(
                "click",
                function () {
                    original.click();

                    window.setTimeout(
                        updateProxy,
                        0
                    );
                }
            );

            sidebar.appendChild(
                proxy
            );
        }


        function updateProxy() {
            const dark =
                document
                    .documentElement
                    .dataset
                    .theme
                === "dark";

            proxy.textContent =
                dark
                    ? "☀️ 日间模式"
                    : "🌙 深夜模式";
        }


        updateProxy();
    }


    function installTabletPortrait() {
        const body =
            document.body;

        const sidebar =
            document.getElementById(
                "sidebar"
            );

        const menuButton =
            document.getElementById(
                "mobileMenuBtn"
            );

        const closeButton =
            document.getElementById(
                "mobileCloseBtn"
            );

        const overlay =
            document.getElementById(
                "mobileOverlay"
            );

        if (
            !body
            || !sidebar
            || !menuButton
            || !closeButton
            || !overlay
        ) {
            return;
        }


        const main =
            document.querySelector(
                ".main-content"
            )
            || document;


        function closeDrawer() {
            body.classList.remove(
                "tablet-sidebar-open"
            );

            sidebar.classList.remove(
                "tablet-a15-open"
            );

            overlay.classList.remove(
                "tablet-a15-open"
            );
        }


        function openDrawer() {
            if (
                !tabletQuery.matches
            ) {
                return;
            }

            body.classList.add(
                "tablet-sidebar-open"
            );

            sidebar.classList.add(
                "tablet-a15-open"
            );

            overlay.classList.add(
                "tablet-a15-open"
            );
        }


        function adaptPage() {
            const path =
                body.dataset.pagePath
                || window.location.pathname;

            if (
                path === "/tasks"
            ) {
                markTasks(main);
            }

            if (
                path === "/strategic"
            ) {
                markStrategic(main);
            }

            if (
                path === "/snapshots"
                ||
                path.startsWith(
                    "/snapshots/"
                )
            ) {
                markSnapshots(main);
            }
        }


        function syncViewport() {
            const active =
                tabletQuery.matches;

            body.classList.toggle(
                "tablet-portrait-a15",
                active
            );

            if (active) {
                closeDrawer();

                adaptPage();

                ensureThemeProxy(
                    sidebar
                );
            } else {
                closeDrawer();
            }
        }


        menuButton.addEventListener(
            "click",
            function () {
                if (
                    tabletQuery.matches
                ) {
                    openDrawer();
                }
            }
        );


        closeButton.addEventListener(
            "click",
            function () {
                if (
                    tabletQuery.matches
                ) {
                    closeDrawer();
                }
            }
        );


        overlay.addEventListener(
            "click",
            function () {
                if (
                    tabletQuery.matches
                ) {
                    closeDrawer();
                }
            }
        );


        sidebar.addEventListener(
            "click",
            function (event) {
                if (
                    !tabletQuery.matches
                ) {
                    return;
                }

                const target =
                    event.target;

                if (
                    target instanceof Element
                    &&
                    target.closest("a")
                ) {
                    closeDrawer();
                }
            }
        );


        document.addEventListener(
            "keydown",
            function (event) {
                if (
                    tabletQuery.matches
                    &&
                    event.key
                    === "Escape"
                ) {
                    closeDrawer();
                }
            }
        );


        if (
            typeof tabletQuery
                .addEventListener
            === "function"
        ) {
            tabletQuery.addEventListener(
                "change",
                syncViewport
            );
        } else if (
            typeof tabletQuery
                .addListener
            === "function"
        ) {
            tabletQuery.addListener(
                syncViewport
            );
        }


        syncViewport();
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            installTabletPortrait
        );
    } else {
        installTabletPortrait();
    }
})();

/* MOBILE_UI_A1_5_R1_1_TABLET_RANGE_FIX */

/*
============================================================
MOBILE_UI_A1_5_R2_TABLET_LANDSCAPE
============================================================
*/

(function () {
    "use strict";


    const landscapeTabletQuery =
        window.matchMedia(
            "(min-width: 901px) "
            + "and (max-width: 1400px) "
            + "and (orientation: landscape) "
            + "and (pointer: coarse)"
        );


    function installLandscapeThemeProxy(
        sidebar
    ) {
        const original =
            document.querySelector(
                ".theme-toggle-button"
            );

        if (!original) {
            return;
        }


        let proxy =
            sidebar.querySelector(
                ".tablet-a15-landscape-theme-proxy"
            );


        if (!proxy) {
            proxy =
                document.createElement(
                    "button"
                );

            proxy.type =
                "button";

            proxy.className =
                "tablet-a15-landscape-theme-proxy";


            proxy.addEventListener(
                "click",
                function () {
                    original.click();

                    window.setTimeout(
                        updateLabel,
                        0
                    );
                }
            );


            sidebar.appendChild(
                proxy
            );
        }


        function updateLabel() {
            const dark =
                document
                    .documentElement
                    .dataset
                    .theme
                === "dark";

            proxy.textContent =
                dark
                    ? "☀️ 日间模式"
                    : "🌙 深夜模式";
        }


        updateLabel();
    }


    function syncLandscapeTablet() {
        const body =
            document.body;

        const sidebar =
            document.getElementById(
                "sidebar"
            );

        if (
            !body
            || !sidebar
        ) {
            return;
        }


        const active =
            landscapeTabletQuery.matches;


        body.classList.toggle(
            "tablet-landscape-a15",
            active
        );


        if (active) {
            installLandscapeThemeProxy(
                sidebar
            );
        }
    }


    if (
        typeof landscapeTabletQuery
            .addEventListener
        === "function"
    ) {
        landscapeTabletQuery
            .addEventListener(
                "change",
                syncLandscapeTablet
            );
    } else if (
        typeof landscapeTabletQuery
            .addListener
        === "function"
    ) {
        landscapeTabletQuery
            .addListener(
                syncLandscapeTablet
            );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            syncLandscapeTablet
        );
    } else {
        syncLandscapeTablet();
    }
})();
