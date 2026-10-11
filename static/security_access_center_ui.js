"use strict";

/* ACCESS CENTER UI CONVERGENCE
 * Accepted A1 / A2 / A2.1 scripts preserved in original execution order.
 */

/* ===== A1 ===== */

(() => {
    "use strict";

    if (
        window.location.pathname
        !== "/security/access-center"
    ) {
        return;
    }

    document.documentElement.classList.add(
        "ac-ux-a1"
    );

    const SCROLL_KEY =
        "v155_access_center_scroll_y";

    const ACTIONS = new Set([
        "set_membership_permission_override",
        "clear_membership_permission_override",
    ]);

    let toastTimer = null;

    function showToast(
        message,
        isError = false
    ) {
        const toast =
            document.getElementById(
                "ac-ux-toast"
            );

        if (!toast) {
            return;
        }

        toast.textContent =
            message || (
                isError
                ? "保存失败"
                : "权限已保存"
            );

        toast.classList.toggle(
            "is-error",
            Boolean(isError)
        );

        toast.classList.add(
            "is-visible"
        );

        if (toastTimer) {
            window.clearTimeout(
                toastTimer
            );
        }

        toastTimer =
            window.setTimeout(
                () => {
                    toast.classList.remove(
                        "is-visible"
                    );
                },
                2200
            );
    }

    function restoreScroll() {
        const stored =
            window.sessionStorage.getItem(
                SCROLL_KEY
            );

        if (!stored) {
            return;
        }

        window.sessionStorage.removeItem(
            SCROLL_KEY
        );

        const value = Number(
            stored
        );

        if (
            !Number.isFinite(value)
        ) {
            return;
        }

        window.requestAnimationFrame(
            () => {
                window.scrollTo({
                    top: value,
                    behavior: "instant",
                });
            }
        );
    }

    function addStatusBar() {
        if (
            document.querySelector(
                ".ac-ux-statusbar"
            )
        ) {
            return;
        }

        const headings = [
            ...document.querySelectorAll(
                "h1, h2"
            ),
        ];

        const title =
            headings.find(
                (node) =>
                    String(
                        node.textContent
                        || ""
                    )
                    .trim()
                    .includes(
                        "权限中心"
                    )
            );

        if (!title) {
            return;
        }

        const bar =
            document.createElement(
                "div"
            );

        bar.className =
            "ac-ux-statusbar";

        bar.innerHTML = `
            <div class="ac-ux-statusbar-main">
                <div class="ac-ux-statusbar-title">
                    权限配置工作台
                </div>
                <div class="ac-ux-statusbar-sub">
                    当前页面支持权限即时保存；
                    调整后不会再跳回页面顶部。
                </div>
            </div>
            <div class="ac-ux-statusbar-badge">
                自动保存已启用
            </div>
        `;

        title.insertAdjacentElement(
            "afterend",
            bar
        );
    }

    function permissionAction(
        form,
        submitter
    ) {
        const data =
            new FormData(
                form
            );

        if (
            submitter
            && submitter.name
        ) {
            data.set(
                submitter.name,
                submitter.value
            );
        }

        return {
            data,
            action:
                String(
                    data.get(
                        "action"
                    )
                    || ""
                ),
        };
    }

    function stateLabel(
        payload
    ) {
        const effect =
            String(
                payload.effect
                || ""
            )
            .trim()
            .toLowerCase();

        if (
            effect === "grant"
            || effect === "allow"
        ) {
            return "允许";
        }

        if (
            effect === "deny"
        ) {
            return "拒绝";
        }

        if (
            effect === "inherit"
        ) {
            return "继承";
        }

        return "已保存";
    }

    function markFormState(
        form,
        message,
        isError = false
    ) {
        let state =
            form.querySelector(
                ".ac-inline-save-state"
            );

        if (!state) {
            state =
                document.createElement(
                    "span"
                );

            state.className =
                "ac-inline-save-state";

            form.appendChild(
                state
            );
        }

        state.textContent =
            message;

        state.classList.toggle(
            "is-error",
            Boolean(isError)
        );
    }

    function nativeFallback(
        form,
        submitter
    ) {
        window.sessionStorage.setItem(
            SCROLL_KEY,
            String(
                window.scrollY
            )
        );

        form.dataset.acNativeSubmit =
            "1";

        if (
            submitter
            && typeof form.requestSubmit
            === "function"
        ) {
            form.requestSubmit(
                submitter
            );

            return;
        }

        form.submit();
    }

    async function handleSubmit(
        event
    ) {
        const form =
            event.currentTarget;

        if (
            form.dataset
            .acNativeSubmit
            === "1"
        ) {
            delete form.dataset
                .acNativeSubmit;

            return;
        }

        const submitter =
            event.submitter
            || null;

        const {
            data,
            action,
        } = permissionAction(
            form,
            submitter
        );

        if (
            !ACTIONS.has(
                action
            )
        ) {
            return;
        }

        if (event.defaultPrevented) {
            return;
        }

        event.preventDefault();

        if (
            form.dataset
            .acSaving
            === "1"
        ) {
            return;
        }

        form.dataset.acSaving =
            "1";

        form.classList.add(
            "ac-saving"
        );

        if (submitter) {
            submitter.disabled =
                true;
        }

        try {
            const response =
                await fetch(
                    form.action
                    || window.location.href,
                    {
                        method:
                            (
                                form.method
                                || "POST"
                            )
                            .toUpperCase(),

                        body:
                            data,

                        credentials:
                            "same-origin",

                        headers: {
                            "X-Requested-With":
                                "XMLHttpRequest",

                            "Accept":
                                "application/json",
                        },
                    }
                );

            const contentType =
                String(
                    response.headers.get(
                        "content-type"
                    )
                    || ""
                );

            if (
                !contentType.includes(
                    "application/json"
                )
            ) {
                throw new Error(
                    "ASYNC_RESPONSE_NOT_JSON"
                );
            }

            const payload =
                await response.json();

            if (
                !response.ok
                || !payload.ok
            ) {
                throw new Error(
                    payload.message
                    || "权限保存失败"
                );
            }

            const label =
                stateLabel(
                    payload
                );

            markFormState(
                form,
                "已保存 · "
                + label,
                false
            );

            showToast(
                "权限已保存 · "
                + label,
                false
            );

            document.dispatchEvent(
                new CustomEvent(
                    "ac:permission-saved",
                    {
                        detail:
                            payload
                    }
                )
            );
        }
        catch (error) {
            const message =
                (
                    error
                    && error.message
                    && error.message
                    !==
                    "ASYNC_RESPONSE_NOT_JSON"
                )
                ? error.message
                : "异步保存不可用，已切换为兼容提交";

            if (
                error
                && error.message
                ===
                "ASYNC_RESPONSE_NOT_JSON"
            ) {
                nativeFallback(
                    form,
                    submitter
                );

                return;
            }

            markFormState(
                form,
                message,
                true
            );

            showToast(
                message,
                true
            );
        }
        finally {
            delete form.dataset
                .acSaving;

            form.classList.remove(
                "ac-saving"
            );

            if (submitter) {
                submitter.disabled =
                    false;
            }
        }
    }

    function bindForms() {
        document
            .querySelectorAll(
                "form"
            )
            .forEach(
                (form) => {
                    if (
                        form.dataset
                        .acAsyncBound
                        === "1"
                    ) {
                        return;
                    }

                    const probe =
                        new FormData(
                            form
                        );

                    const hasPermission =
                        Boolean(
                            form.querySelector(
                                '[name="permission_key"]'
                            )
                        );

                    const hasAction =
                        Boolean(
                            form.querySelector(
                                '[name="action"]'
                            )
                        );

                    if (
                        !hasPermission
                        || !hasAction
                    ) {
                        return;
                    }

                    form.dataset
                        .acAsyncBound =
                        "1";

                    form.classList.add(
                        "ac-permission-async-form"
                    );

                    form.addEventListener(
                        "submit",
                        handleSubmit
                    );
                }
            );
    }

    restoreScroll();
    addStatusBar();
    bindForms();
})();

/* ===== A2 ===== */

(() => {
    "use strict";

    const PATH =
        "/security/access-center";

    if (
        window.location.pathname
        !== PATH
    ) {
        return;
    }

    function text(node) {
        return String(
            node
            ? node.textContent
            : ""
        ).trim();
    }

    function create(
        tag,
        className,
        value
    ) {
        const node =
            document.createElement(
                tag
            );

        if (className) {
            node.className =
                className;
        }

        if (
            value !== undefined
            && value !== null
        ) {
            node.textContent =
                value;
        }

        return node;
    }

    function getState(row) {
        const state =
            row.querySelector(
                ".ac-state"
            );

        const roleBaseline =
            Boolean(
                state
                && state.querySelector(
                    ".ac-badge-role"
                )
            );

        let effect =
            "inherit";

        if (
            state
            && state.querySelector(
                ".ac-badge-grant"
            )
        ) {
            effect = "grant";
        }
        else if (
            state
            && state.querySelector(
                ".ac-badge-deny"
            )
        ) {
            effect = "deny";
        }

        const effective =
            Boolean(
                state
                && state.querySelector(
                    ".ac-badge-effective"
                )
            );

        return {
            state,
            roleBaseline,
            effect,
            effective,
        };
    }

    function sourceLabel(effect) {
        if (
            effect === "grant"
        ) {
            return "单独允许";
        }

        if (
            effect === "deny"
        ) {
            return "单独禁止";
        }

        return "跟随角色";
    }

    function renderSummary(row) {
        const finalNode =
            row.querySelector(
                ".ac-a2-final"
            );

        const sourceNode =
            row.querySelector(
                ".ac-a2-source"
            );

        if (
            !finalNode
            || !sourceNode
        ) {
            return;
        }

        const effective =
            row.dataset
                .acEffective
            === "1";

        const effect =
            row.dataset
                .acEffect
            || "inherit";

        finalNode.textContent =
            effective
            ? "可用"
            : "不可用";

        finalNode.classList.toggle(
            "is-on",
            effective
        );

        finalNode.classList.toggle(
            "is-off",
            !effective
        );

        sourceNode.textContent =
            sourceLabel(
                effect
            );

        sourceNode.classList.toggle(
            "is-adjusted",
            effect !== "inherit"
        );
    }

    function rebuildState(
        row,
        effect,
        effective
    ) {
        const state =
            row.querySelector(
                ".ac-state"
            );

        if (!state) {
            return;
        }

        const roleBaseline =
            row.dataset
                .acRoleBaseline
            === "1";

        state.replaceChildren();

        if (roleBaseline) {
            const role =
                create(
                    "span",
                    "ac-badge ac-badge-role",
                    "角色提供"
                );

            state.appendChild(
                role
            );
        }

        if (
            effect === "grant"
        ) {
            state.appendChild(
                create(
                    "span",
                    "ac-badge ac-badge-grant",
                    "单独允许"
                )
            );
        }
        else if (
            effect === "deny"
        ) {
            state.appendChild(
                create(
                    "span",
                    "ac-badge ac-badge-deny",
                    "单独禁止"
                )
            );
        }
        else {
            state.appendChild(
                create(
                    "span",
                    "ac-badge",
                    "跟随角色"
                )
            );
        }

        state.appendChild(
            create(
                "span",
                (
                    effective
                    ? "ac-badge ac-badge-effective"
                    : "ac-badge ac-badge-off"
                ),
                (
                    effective
                    ? "最终可用"
                    : "最终不可用"
                )
            )
        );
    }

    function updateGroupMetrics(
        group
    ) {
        if (!group) {
            return;
        }

        const rows = [
            ...group.querySelectorAll(
                ".ac-permission"
            ),
        ];

        if (!rows.length) {
            return;
        }

        const effectiveCount =
            rows.filter(
                (row) =>
                    row.dataset
                        .acEffective
                    === "1"
            ).length;

        const adjustedCount =
            rows.filter(
                (row) =>
                    row.dataset
                        .acEffect
                    !== "inherit"
            ).length;

        const metrics =
            group.querySelector(
                ".ac-group-metrics"
            );

        if (!metrics) {
            return;
        }

        [
            ...metrics.children,
        ].forEach(
            (item) => {
                const value =
                    text(item);

                if (
                    value.startsWith(
                        "有效 "
                    )
                ) {
                    item.textContent =
                        "可用 "
                        + effectiveCount
                        + "/"
                        + rows.length;
                }
                else if (
                    value.startsWith(
                        "单独调整 "
                    )
                ) {
                    item.textContent =
                        "单独调整 "
                        + adjustedCount;
                }
                else if (
                    value.startsWith(
                        "可调整 "
                    )
                ) {
                    item.dataset
                        .acA2Grantable =
                        "1";
                }
            }
        );
    }

    function enhanceRow(row) {
        if (
            row.dataset
                .acA2Enhanced
            === "1"
        ) {
            return;
        }

        const name =
            row.querySelector(
                ".ac-permission-name"
            );

        const state =
            row.querySelector(
                ".ac-state"
            );

        const actions =
            row.querySelector(
                ".ac-actions"
            );

        if (
            !name
            || !state
        ) {
            return;
        }

        const initial =
            getState(
                row
            );

        row.dataset
            .acRoleBaseline =
            initial.roleBaseline
            ? "1"
            : "0";

        row.dataset
            .acEffect =
            initial.effect;

        row.dataset
            .acEffective =
            initial.effective
            ? "1"
            : "0";

        const permissionInput =
            row.querySelector(
                '[name="permission_key"]'
            );

        if (permissionInput) {
            row.dataset
                .acPermissionKey =
                String(
                    permissionInput.value
                    || ""
                );
        }

        const summary =
            create(
                "div",
                "ac-a2-summary"
            );

        summary.appendChild(
            create(
                "span",
                "ac-a2-final"
            )
        );

        summary.appendChild(
            create(
                "span",
                "ac-a2-source"
            )
        );

        const toggle =
            create(
                "button",
                "ac-a2-adjust",
                actions
                ? "调整"
                : "详情"
            );

        toggle.type =
            "button";

        toggle.setAttribute(
            "aria-expanded",
            "false"
        );

        const detail =
            create(
                "div",
                "ac-a2-detail"
            );

        state.parentNode.insertBefore(
            summary,
            state
        );

        summary.parentNode.insertBefore(
            toggle,
            state
        );

        summary.parentNode.insertBefore(
            detail,
            state
        );

        detail.appendChild(
            state
        );

        if (actions) {
            detail.appendChild(
                actions
            );
        }

        toggle.addEventListener(
            "click",
            () => {
                const open =
                    !detail.classList
                        .contains(
                            "is-open"
                        );

                detail.classList.toggle(
                    "is-open",
                    open
                );

                toggle.setAttribute(
                    "aria-expanded",
                    open
                    ? "true"
                    : "false"
                );

                toggle.textContent =
                    open
                    ? "收起"
                    : (
                        actions
                        ? "调整"
                        : "详情"
                    );
            }
        );

        row.dataset
            .acA2Enhanced =
            "1";

        renderSummary(
            row
        );
    }

    function simplifyHeader() {
        [
            ...document.querySelectorAll(
                ".ac-panel-title"
            ),
        ].forEach(
            (panel) => {
                const heading =
                    panel.querySelector(
                        "h2"
                    );

                if (
                    text(heading)
                    !==
                    "成员最终权限"
                ) {
                    return;
                }

                heading.textContent =
                    "权限配置";

                const paragraph =
                    panel.querySelector(
                        "p"
                    );

                if (paragraph) {
                    paragraph.textContent =
                        "先看最终结果；只有需要例外时再做单独调整。";
                }
            }
        );
    }

    function collapseLegend() {
        const legend =
            document.querySelector(
                ".ac-legend"
            );

        if (
            !legend
            || legend.closest(
                ".ac-a2-help"
            )
        ) {
            return;
        }

        const help =
            document.createElement(
                "details"
            );

        help.className =
            "ac-a2-help";

        const summary =
            document.createElement(
                "summary"
            );

        summary.textContent =
            "状态说明";

        legend.parentNode.insertBefore(
            help,
            legend
        );

        help.appendChild(
            summary
        );

        help.appendChild(
            legend
        );
    }

    function filterControls() {
        const buttons = [
            ...document.querySelectorAll(
                "button"
            ),
        ];

        const source = {
            all:
                buttons.find(
                    (button) =>
                        text(button)
                        === "全部"
                ),

            available:
                buttons.find(
                    (button) =>
                        text(button)
                        === "仅看可用"
                ),

            adjusted:
                buttons.find(
                    (button) =>
                        text(button)
                        === "仅看单独调整"
                ),
        };

        if (
            !source.all
            || !source.adjusted
        ) {
            return null;
        }

        const result = {};

        function replaceButton(
            original,
            mode,
            label
        ) {
            if (!original) {
                return null;
            }

            const clone =
                original.cloneNode(
                    true
                );

            clone.textContent =
                label;

            clone.dataset
                .acA2Filter =
                mode;

            clone.classList.remove(
                "ac-a2-filter-active"
            );

            original.replaceWith(
                clone
            );

            return clone;
        }

        result.all =
            replaceButton(
                source.all,
                "all",
                "全部"
            );

        result.unavailable =
            replaceButton(
                source.available,
                "unavailable",
                "只看不可用"
            );

        result.adjusted =
            replaceButton(
                source.adjusted,
                "adjusted",
                "只看单独调整"
            );

        return result;
    }

    function replaceSearch() {
        const input =
            document.querySelector(
                '.ac-search input, input[placeholder*="搜索页面"]'
            );

        if (!input) {
            return null;
        }

        const clone =
            input.cloneNode(
                true
            );

        clone.value =
            input.value;

        input.replaceWith(
            clone
        );

        return clone;
    }

    function initFilter() {
        const controls =
            filterControls();

        const search =
            replaceSearch();

        if (
            !controls
            && !search
        ) {
            return;
        }

        let mode =
            "all";

        function apply() {
            const query =
                String(
                    search
                    ? search.value
                    : ""
                )
                .trim()
                .toLocaleLowerCase();

            [
                ...document.querySelectorAll(
                    ".ac-permission"
                ),
            ].forEach(
                (row) => {
                    const effective =
                        row.dataset
                            .acEffective
                        === "1";

                    const adjusted =
                        row.dataset
                            .acEffect
                        !== "inherit";

                    const matchesMode =
                        mode === "all"
                        || (
                            mode
                            === "adjusted"
                            && adjusted
                        )
                        || (
                            mode
                            === "unavailable"
                            && !effective
                        );

                    const matchesSearch =
                        !query
                        || text(row)
                            .toLocaleLowerCase()
                            .includes(
                                query
                            );

                    row.classList.toggle(
                        "ac-a2-hidden",
                        !(
                            matchesMode
                            && matchesSearch
                        )
                    );
                }
            );

            [
                ...document.querySelectorAll(
                    ".ac-group"
                ),
            ].forEach(
                (group) => {
                    const visible =
                        [
                            ...group
                                .querySelectorAll(
                                    ".ac-permission"
                                ),
                        ]
                        .some(
                            (row) =>
                                !row.classList
                                    .contains(
                                        "ac-a2-hidden"
                                    )
                        );

                    group.classList.toggle(
                        "ac-a2-hidden",
                        !visible
                    );

                    if (
                        query
                        && visible
                    ) {
                        group.open =
                            true;
                    }
                }
            );

            if (controls) {
                Object.values(
                    controls
                ).forEach(
                    (button) => {
                        if (!button) {
                            return;
                        }

                        button.classList.toggle(
                            "ac-a2-filter-active",
                            button.dataset
                                .acA2Filter
                            === mode
                        );
                    }
                );
            }
        }

        if (controls) {
            Object.values(
                controls
            ).forEach(
                (button) => {
                    if (!button) {
                        return;
                    }

                    button.addEventListener(
                        "click",
                        () => {
                            mode =
                                button.dataset
                                    .acA2Filter
                                || "all";

                            apply();
                        }
                    );
                }
            );

            if (controls.all) {
                controls.all
                    .classList.add(
                        "ac-a2-filter-active"
                    );
            }
        }

        if (search) {
            search.addEventListener(
                "input",
                apply
            );
        }

        document.addEventListener(
            "ac:a2-refresh-filter",
            apply
        );
    }

    function handleSaved(
        event
    ) {
        const payload =
            event.detail
            || {};

        const key =
            String(
                payload.permission_key
                || ""
            );

        if (!key) {
            return;
        }

        const row = [
            ...document.querySelectorAll(
                ".ac-permission"
            ),
        ].find(
            (candidate) =>
                candidate.dataset
                    .acPermissionKey
                === key
        );

        if (!row) {
            return;
        }

        const effect =
            String(
                payload.effect
                || "inherit"
            )
            .trim()
            .toLowerCase();

        const roleBaseline =
            row.dataset
                .acRoleBaseline
            === "1";

        let effective =
            roleBaseline;

        if (
            effect === "grant"
            || effect === "allow"
        ) {
            effective =
                true;
        }
        else if (
            effect === "deny"
        ) {
            effective =
                false;
        }

        row.dataset
            .acEffect =
            (
                effect === "allow"
                ? "grant"
                : effect
            );

        row.dataset
            .acEffective =
            effective
            ? "1"
            : "0";

        rebuildState(
            row,
            row.dataset
                .acEffect,
            effective
        );

        renderSummary(
            row
        );

        updateGroupMetrics(
            row.closest(
                ".ac-group"
            )
        );

        document.dispatchEvent(
            new CustomEvent(
                "ac:a2-refresh-filter"
            )
        );
    }

    function init() {
        document
            .documentElement
            .classList.add(
                "ac-ux-a2"
            );

        simplifyHeader();
        collapseLegend();

        [
            ...document.querySelectorAll(
                ".ac-permission"
            ),
        ].forEach(
            enhanceRow
        );

        [
            ...document.querySelectorAll(
                ".ac-group"
            ),
        ].forEach(
            updateGroupMetrics
        );

        initFilter();

        document.addEventListener(
            "ac:permission-saved",
            handleSaved
        );
    }

    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            init,
            {
                once:
                    true
            }
        );
    }
    else {
        init();
    }
})();

/* ===== A2_1 ===== */

(() => {
    "use strict";

    if (
        window.location.pathname
        !== "/security/access-center"
    ) {
        return;
    }

    const STATE = {
        availableCard:
            null,

        adjustedCard:
            null,
    };

    function text(node) {
        return String(
            node
            ? node.textContent
            : ""
        ).trim();
    }

    function cleanMemberInternalId() {
        [
            ...document.querySelectorAll(
                ".ac-member-meta"
            ),
        ].forEach(
            (node) => {
                const before =
                    text(
                        node
                    );

                if (!before) {
                    return;
                }

                const after =
                    before
                    .replace(
                        /\s*·\s*membership\s*#\d+\s*/gi,
                        ""
                    )
                    .replace(
                        /\s*·\s*$/g,
                        ""
                    )
                    .trim();

                if (
                    after
                    && after !== before
                ) {
                    node.textContent =
                        after;
                }
            }
        );
    }

    function findStatByLabel(
        label
    ) {
        return [
            ...document.querySelectorAll(
                ".ac-counts .ac-stat"
            ),
        ].find(
            (card) => {
                const labelNode =
                    card.querySelector(
                        "span"
                    );

                return (
                    text(
                        labelNode
                    )
                    === label
                );
            }
        ) || null;
    }

    function simplifyTopStats() {
        const baseline =
            findStatByLabel(
                "角色基线"
            );

        const overridable =
            findStatByLabel(
                "可覆盖"
            );

        const adjusted =
            findStatByLabel(
                "单独调整"
            );

        const finalEffective =
            findStatByLabel(
                "最终有效"
            )
            || findStatByLabel(
                "当前可用"
            );

        [
            baseline,
            overridable,
        ].forEach(
            (card) => {
                if (!card) {
                    return;
                }

                card.dataset
                    .acA21Hidden =
                    "1";

                card.hidden =
                    true;
            }
        );

        if (finalEffective) {
            const label =
                finalEffective
                    .querySelector(
                        "span"
                    );

            if (label) {
                label.textContent =
                    "当前可用";
            }
        }

        STATE.availableCard =
            finalEffective;

        STATE.adjustedCard =
            adjusted;

        if (
            finalEffective
            && adjusted
            && finalEffective.parentNode
            === adjusted.parentNode
        ) {
            adjusted.parentNode
                .insertBefore(
                    finalEffective,
                    adjusted
                );
        }
    }

    function permissionRows() {
        const rows = [
            ...document.querySelectorAll(
                ".ac-group .ac-permission"
            ),
        ];

        const unique =
            new Map();

        let anonymous =
            0;

        rows.forEach(
            (row) => {
                const key =
                    String(
                        row.dataset
                            .acPermissionKey
                        || ""
                    ).trim();

                if (key) {
                    if (
                        !unique.has(
                            key
                        )
                    ) {
                        unique.set(
                            key,
                            row
                        );
                    }

                    return;
                }

                anonymous +=
                    1;

                unique.set(
                    "__anonymous_"
                    + anonymous,
                    row
                );
            }
        );

        return [
            ...unique.values(),
        ];
    }

    function refreshTopStats() {
        const rows =
            permissionRows();

        if (!rows.length) {
            return;
        }

        const available =
            rows.filter(
                (row) =>
                    row.dataset
                        .acEffective
                    === "1"
            ).length;

        const adjusted =
            rows.filter(
                (row) => {
                    const effect =
                        String(
                            row.dataset
                                .acEffect
                            || "inherit"
                        );

                    return (
                        effect
                        !== "inherit"
                    );
                }
            ).length;

        if (
            STATE.availableCard
        ) {
            const strong =
                STATE.availableCard
                    .querySelector(
                        "strong"
                    );

            if (strong) {
                strong.textContent =
                    String(
                        available
                    );
            }
        }

        if (
            STATE.adjustedCard
        ) {
            const strong =
                STATE.adjustedCard
                    .querySelector(
                        "strong"
                    );

            if (strong) {
                strong.textContent =
                    String(
                        adjusted
                    );
            }
        }
    }

    function hideGrantableMetrics() {
        [
            ...document.querySelectorAll(
                ".ac-group-metrics > *"
            ),
        ].forEach(
            (item) => {
                if (
                    !text(item)
                    .startsWith(
                        "可调整 "
                    )
                ) {
                    return;
                }

                item.dataset
                    .acA21Hidden =
                    "1";

                item.hidden =
                    true;

                item.style
                    .setProperty(
                        "display",
                        "none",
                        "important"
                    );
            }
        );
    }

    function refineAdjustButtons() {
        [
            ...document.querySelectorAll(
                ".ac-a2-adjust"
            ),
        ].forEach(
            (button) => {
                if (
                    button.dataset
                        .acA21Bound
                    === "1"
                ) {
                    return;
                }

                function syncLabel() {
                    const expanded =
                        button.getAttribute(
                            "aria-expanded"
                        )
                        === "true";

                    button.textContent =
                        expanded
                        ? "完成"
                        : "调整";
                }

                syncLabel();

                button.addEventListener(
                    "click",
                    () => {
                        window
                            .requestAnimationFrame(
                                syncLabel
                            );
                    }
                );

                button.dataset
                    .acA21Bound =
                    "1";
            }
        );
    }

    function refreshAfterPermissionSave() {
        /*
         * A2 的保存监听器会先更新
         * acEffect / acEffective，
         * A2.1 再重新汇总顶部统计。
         */
        window
            .requestAnimationFrame(
                () => {
                    refreshTopStats();
                    hideGrantableMetrics();
                }
            );
    }

    function init() {
        document.documentElement
            .classList.add(
                "ac-ux-a21"
            );

        cleanMemberInternalId();

        simplifyTopStats();

        hideGrantableMetrics();

        refineAdjustButtons();

        refreshTopStats();

        document.addEventListener(
            "ac:permission-saved",
            refreshAfterPermissionSave
        );
    }

    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            init,
            {
                once:
                    true
            }
        );
    }
    else {
        init();
    }
})();
