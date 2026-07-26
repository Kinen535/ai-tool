(() => {
    "use strict";

    const GROUP_STORAGE_KEY = "compareAttendanceGroupsExpandedV1";
    const COLUMN_STORAGE_KEY = "compareAttendanceColumnsV1";
    const PRESET_STORAGE_KEY = "compareAttendancePresetV1";
    const SORT_STORAGE_KEY = "compareAttendanceSortV1";

    const LOCKED_COLUMNS = [
        "成员",
        "分组"
    ];

    const PRESETS = {
        management: [
            "成员",
            "分组",
            "综合考勤状态",
            "战功增长",
            "助攻增长",
            "捐献增长",
            "势力增长",
            "执行状态",
            "违规标记",
            "状态",
            "建议",
            "评分",
            "风险原因"
        ],
        attendance: [
            "成员",
            "分组",
            "综合考勤状态",
            "战功考勤状态",
            "助攻考勤状态",
            "捐献考勤状态",
            "战功增长",
            "助攻增长",
            "捐献增长",
            "考勤范围状态",
            "是否有基线",
            "考勤排除原因"
        ],
        full: null
    };

    function readStorage(key, fallbackValue) {
        try {
            const rawValue = window.localStorage.getItem(key);

            if (!rawValue) {
                return fallbackValue;
            }

            return JSON.parse(rawValue);
        } catch (error) {
            console.warn("无法读取本地表格设置", error);

            return fallbackValue;
        }
    }

    function writeStorage(key, value) {
        try {
            window.localStorage.setItem(
                key,
                JSON.stringify(value)
            );
        } catch (error) {
            console.warn("无法保存本地表格设置", error);
        }
    }

    function readGroupExpandedState() {
        try {
            const value = window.localStorage.getItem(
                GROUP_STORAGE_KEY
            );

            if (value === "collapsed") {
                return false;
            }

            if (value === "expanded") {
                return true;
            }
        } catch (error) {
            console.warn("无法读取考勤看板本地状态", error);
        }

        return true;
    }

    function saveGroupExpandedState(expanded) {
        try {
            window.localStorage.setItem(
                GROUP_STORAGE_KEY,
                expanded ? "expanded" : "collapsed"
            );
        } catch (error) {
            console.warn("无法保存考勤看板本地状态", error);
        }
    }

    function initialiseGroupPanel(dashboard) {
        const toggleButton = dashboard.querySelector(
            "[data-ca-toggle-groups]"
        );

        const groupPanel = dashboard.querySelector(
            "[data-ca-groups]"
        );

        if (!toggleButton || !groupPanel) {
            return;
        }

        const updateState = (expanded, persist) => {
            groupPanel.classList.toggle(
                "ca-is-hidden",
                !expanded
            );

            toggleButton.setAttribute(
                "aria-expanded",
                expanded ? "true" : "false"
            );

            toggleButton.textContent = expanded
                ? "收起分组概览"
                : "展开分组概览";

            if (persist) {
                saveGroupExpandedState(expanded);
            }
        };

        updateState(
            readGroupExpandedState(),
            false
        );

        toggleButton.addEventListener(
            "click",
            () => {
                const expanded = (
                    toggleButton.getAttribute(
                        "aria-expanded"
                    ) !== "true"
                );

                updateState(
                    expanded,
                    true
                );
            }
        );
    }

    function getHeaders(table) {
        return Array.from(
            table.querySelectorAll(
                "thead th[data-column]"
            )
        );
    }

    function getRows(table) {
        return Array.from(
            table.querySelectorAll(
                "tbody tr.selectable-row"
            )
        );
    }

    function getAllColumns(table) {
        return getHeaders(table)
            .map((header) => header.dataset.column)
            .filter(Boolean);
    }

    function normaliseVisibleColumns(table, columns) {
        const allColumns = getAllColumns(table);

        const requested = Array.isArray(columns)
            ? columns
            : [];

        const visible = new Set(
            requested.filter(
                (column) => allColumns.includes(column)
            )
        );

        LOCKED_COLUMNS.forEach(
            (column) => visible.add(column)
        );

        return allColumns.filter(
            (column) => visible.has(column)
        );
    }

    function columnsForPreset(table, presetName) {
        const allColumns = getAllColumns(table);

        if (
            presetName === "full"
            || !PRESETS[presetName]
        ) {
            return allColumns;
        }

        return normaliseVisibleColumns(
            table,
            PRESETS[presetName]
        );
    }

    function getCellByColumn(row, context, column) {
        const index = context.columnIndexes.get(column);

        if (
            typeof index !== "number"
            || index < 0
        ) {
            return null;
        }

        return row.children[index] || null;
    }

    function applyColumnVisibility(
        context,
        visibleColumns,
        persist
    ) {
        const normalised = normaliseVisibleColumns(
            context.table,
            visibleColumns
        );

        const visible = new Set(normalised);

        context.headers.forEach(
            (header) => {
                const column = header.dataset.column;

                header.classList.toggle(
                    "ca-column-hidden",
                    !visible.has(column)
                );
            }
        );

        context.rows.forEach(
            (row) => {
                Array.from(row.children).forEach(
                    (cell, index) => {
                        const header = context.headers[index];

                        if (!header) {
                            return;
                        }

                        const column = header.dataset.column;

                        cell.classList.toggle(
                            "ca-column-hidden",
                            !visible.has(column)
                        );
                    }
                );
            }
        );

        context.visibleColumns = normalised;

        context.columnMenu
            .querySelectorAll(
                "input[data-ca-column-toggle]"
            )
            .forEach(
                (checkbox) => {
                    checkbox.checked = visible.has(
                        checkbox.value
                    );
                }
            );

        if (persist) {
            writeStorage(
                COLUMN_STORAGE_KEY,
                normalised
            );

            writeStorage(
                PRESET_STORAGE_KEY,
                "custom"
            );

            context.presetSelect.value = "custom";
        }
    }

    function buildColumnMenu(context) {
        context.columnMenu.innerHTML = "";

        context.headers.forEach(
            (header) => {
                const column = header.dataset.column;

                if (!column) {
                    return;
                }

                const label = document.createElement(
                    "label"
                );

                label.className = "ca-column-option";

                const checkbox = document.createElement(
                    "input"
                );

                checkbox.type = "checkbox";
                checkbox.value = column;
                checkbox.dataset.caColumnToggle = "true";

                const locked = LOCKED_COLUMNS.includes(
                    column
                );

                checkbox.disabled = locked;
                checkbox.checked = true;

                const text = document.createElement(
                    "span"
                );

                text.textContent = locked
                    ? `${column}（固定）`
                    : column;

                label.append(
                    checkbox,
                    text
                );

                context.columnMenu.appendChild(label);

                checkbox.addEventListener(
                    "change",
                    () => {
                        const selected = Array.from(
                            context.columnMenu.querySelectorAll(
                                "input[data-ca-column-toggle]:checked"
                            )
                        ).map(
                            (item) => item.value
                        );

                        applyColumnVisibility(
                            context,
                            selected,
                            true
                        );
                    }
                );
            }
        );
    }

    function parseNumericValue(value) {
        const normalised = String(value || "")
            .replace(/,/g, "")
            .replace(/%/g, "")
            .trim();

        if (!normalised || normalised === "-") {
            return Number.NEGATIVE_INFINITY;
        }

        const numericValue = Number(normalised);

        return Number.isFinite(numericValue)
            ? numericValue
            : Number.NEGATIVE_INFINITY;
    }

    function readCellValue(
        row,
        context,
        column
    ) {
        const cell = getCellByColumn(
            row,
            context,
            column
        );

        if (!cell) {
            return "";
        }

        const explicitValue = cell.dataset.sortValue;

        if (
            typeof explicitValue === "string"
            && explicitValue !== ""
        ) {
            return explicitValue;
        }

        return cell.textContent.trim();
    }

    function compareValues(
        firstValue,
        secondValue,
        sortType
    ) {
        if (sortType === "number") {
            return (
                parseNumericValue(firstValue)
                - parseNumericValue(secondValue)
            );
        }

        return String(firstValue).localeCompare(
            String(secondValue),
            "zh-CN",
            {
                numeric: true,
                sensitivity: "base"
            }
        );
    }

    function updateSortIndicators(
        context,
        sortState
    ) {
        context.headers.forEach(
            (header) => {
                const button = header.querySelector(
                    "[data-ca-sort-column]"
                );

                const indicator = header.querySelector(
                    "[data-ca-sort-indicator]"
                );

                if (!button || !indicator) {
                    return;
                }

                const active = (
                    header.dataset.column
                    === sortState.column
                );

                button.classList.toggle(
                    "is-active",
                    active
                );

                indicator.textContent = active
                    ? (
                        sortState.direction === "asc"
                            ? "↑"
                            : "↓"
                    )
                    : "↕";
            }
        );
    }

    function applySort(
        context,
        sortState,
        persist
    ) {
        const header = context.headers.find(
            (item) => (
                item.dataset.column
                === sortState.column
            )
        );

        if (!header) {
            return;
        }

        const sortType = (
            header.dataset.sortType
            || "text"
        );

        const directionMultiplier = (
            sortState.direction === "desc"
                ? -1
                : 1
        );

        const indexedRows = context.rows.map(
            (row, index) => ({
                row,
                index
            })
        );

        indexedRows.sort(
            (first, second) => {
                const firstValue = readCellValue(
                    first.row,
                    context,
                    sortState.column
                );

                const secondValue = readCellValue(
                    second.row,
                    context,
                    sortState.column
                );

                let result = compareValues(
                    firstValue,
                    secondValue,
                    sortType
                );

                result *= directionMultiplier;

                if (result !== 0) {
                    return result;
                }

                const fallbackColumns = [
                    "考勤排序等级",
                    "战功增长",
                    "助攻增长",
                    "捐献增长",
                    "成员"
                ];

                for (
                    const fallbackColumn
                    of fallbackColumns
                ) {
                    if (
                        fallbackColumn
                        === sortState.column
                    ) {
                        continue;
                    }

                    const fallbackHeader = (
                        context.headers.find(
                            (item) => (
                                item.dataset.column
                                === fallbackColumn
                            )
                        )
                    );

                    if (!fallbackHeader) {
                        continue;
                    }

                    const fallbackType = (
                        fallbackHeader.dataset.sortType
                        || "text"
                    );

                    const fallbackResult = compareValues(
                        readCellValue(
                            first.row,
                            context,
                            fallbackColumn
                        ),
                        readCellValue(
                            second.row,
                            context,
                            fallbackColumn
                        ),
                        fallbackType
                    );

                    if (fallbackResult !== 0) {
                        if (
                            fallbackColumn
                            === "考勤排序等级"
                            || fallbackColumn
                            === "成员"
                        ) {
                            return fallbackResult;
                        }

                        return -fallbackResult;
                    }
                }

                return first.index - second.index;
            }
        );

        indexedRows.forEach(
            ({ row }) => {
                context.tbody.appendChild(row);
            }
        );

        context.sortState = {
            column: sortState.column,
            direction: sortState.direction
        };

        updateSortIndicators(
            context,
            context.sortState
        );

        if (persist) {
            writeStorage(
                SORT_STORAGE_KEY,
                context.sortState
            );
        }
    }

    function rowMatchesFilter(row, filterValue) {
        if (filterValue === "all") {
            return true;
        }

        const values = [
            row.getAttribute(
                "data-ca-attendance-status"
            ),
            row.getAttribute(
                "data-ca-battle-status"
            ),
            row.getAttribute(
                "data-ca-assist-status"
            ),
            row.getAttribute(
                "data-ca-donate-status"
            ),
            row.getAttribute(
                "data-ca-scope-status"
            )
        ].filter(Boolean);

        if (filterValue === "无基线") {
            return (
                row.getAttribute(
                    "data-ca-has-baseline"
                ) === "0"
                || values.includes("无基线")
            );
        }

        return values.includes(filterValue);
    }

    function updateVisibleCount(context) {
        const visibleRows = context.rows.filter(
            (row) => (
                !row.classList.contains(
                    "ca-smart-filter-hidden"
                )
            )
        );

        context.countElement.textContent = (
            `当前显示 ${visibleRows.length} 人`
        );

        context.emptyElement.classList.toggle(
            "ca-is-hidden",
            visibleRows.length !== 0
        );
    }

    function applyStatusFilter(
        context,
        filterValue
    ) {
        context.rows.forEach(
            (row) => {
                row.classList.toggle(
                    "ca-smart-filter-hidden",
                    !rowMatchesFilter(
                        row,
                        filterValue
                    )
                );
            }
        );

        context.filterButtons.forEach(
            (button) => {
                button.classList.toggle(
                    "is-active",
                    button.dataset.caStatusFilter
                    === filterValue
                );
            }
        );

        context.activeFilter = filterValue;

        updateVisibleCount(context);
    }

    function csvEscape(value) {
        const text = String(value ?? "")
            .replace(/\r?\n/g, " ")
            .trim();

        if (
            text.includes(",")
            || text.includes('"')
            || text.includes("\n")
        ) {
            return (
                '"'
                + text.replace(/"/g, '""')
                + '"'
            );
        }

        return text;
    }

    function exportFilename(disposition) {
        const utf8Match = disposition.match(
            /filename\*=UTF-8''([^;]+)/i
        );

        if (utf8Match) {
            return decodeURIComponent(utf8Match[1]);
        }

        const plainMatch = disposition.match(
            /filename="?([^";]+)"?/i
        );

        return plainMatch
            ? plainMatch[1]
            : "compare-analysis.xlsx";
    }

    async function exportExcel(
        context,
        mode,
        button
    ) {
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "生成中...";

        try {
            const response = await fetch(
                "/compare/export.xlsx",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        mode,
                        client_state: {
                            status_filter:
                                context.activeFilter || "all",
                            sort_column:
                                context.sortState
                                    ? context.sortState.column
                                    : "",
                            sort_direction:
                                context.sortState
                                    ? context.sortState.direction
                                    : "asc",
                            visible_columns:
                                Array.isArray(context.visibleColumns)
                                    ? context.visibleColumns
                                    : []
                        }
                    })
                }
            );

            if (!response.ok) {
                const message = await response.text();
                throw new Error(
                    message
                    || `导出失败（${response.status}）`
                );
            }

            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const link = document.createElement("a");

            link.href = objectUrl;
            link.download = exportFilename(
                response.headers.get(
                    "Content-Disposition"
                ) || ""
            );

            document.body.appendChild(link);
            link.click();
            link.remove();

            window.setTimeout(
                () => URL.revokeObjectURL(objectUrl),
                0
            );
        } catch (error) {
            window.alert(
                error instanceof Error
                    ? error.message
                    : "Excel导出失败"
            );
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    function resetTable(context) {
        const columns = columnsForPreset(
            context.table,
            "management"
        );

        applyColumnVisibility(
            context,
            columns,
            false
        );

        context.presetSelect.value = "management";

        writeStorage(
            PRESET_STORAGE_KEY,
            "management"
        );

        writeStorage(
            COLUMN_STORAGE_KEY,
            columns
        );

        const defaultSort = {
            column: "考勤排序等级",
            direction: "asc"
        };

        applySort(
            context,
            defaultSort,
            true
        );

        applyStatusFilter(
            context,
            "all"
        );
    }

    function initialiseMemberTable() {
        const table = document.querySelector(
            "[data-ca-member-table]"
        );

        const toolbar = document.querySelector(
            "[data-ca-smart-table-toolbar]"
        );

        if (!table || !toolbar) {
            return;
        }

        const headers = getHeaders(table);
        const rows = getRows(table);
        const tbody = table.querySelector("tbody");

        const columnMenu = toolbar.querySelector(
            "[data-ca-column-menu]"
        );

        const presetSelect = toolbar.querySelector(
            "[data-ca-table-preset]"
        );

        const countElement = toolbar.querySelector(
            "[data-ca-table-count]"
        );

        const emptyElement = document.querySelector(
            "[data-ca-member-table-empty]"
        );

        const filterButtons = Array.from(
            toolbar.querySelectorAll(
                "[data-ca-status-filter]"
            )
        );

        if (
            !tbody
            || !columnMenu
            || !presetSelect
            || !countElement
            || !emptyElement
        ) {
            console.warn(
                "成员智能表格DOM契约不完整"
            );

            return;
        }

        const columnIndexes = new Map();

        headers.forEach(
            (header, index) => {
                columnIndexes.set(
                    header.dataset.column,
                    index
                );
            }
        );

        const context = {
            table,
            toolbar,
            headers,
            rows,
            tbody,
            columnMenu,
            presetSelect,
            countElement,
            emptyElement,
            filterButtons,
            columnIndexes,
            visibleColumns: [],
            activeFilter: "all",
            sortState: null
        };

        buildColumnMenu(context);

        const storedPreset = readStorage(
            PRESET_STORAGE_KEY,
            "management"
        );

        const validPreset = (
            storedPreset === "management"
            || storedPreset === "attendance"
            || storedPreset === "full"
            || storedPreset === "custom"
        )
            ? storedPreset
            : "management";

        let visibleColumns;

        if (validPreset === "custom") {
            visibleColumns = readStorage(
                COLUMN_STORAGE_KEY,
                columnsForPreset(
                    table,
                    "management"
                )
            );
        } else {
            visibleColumns = columnsForPreset(
                table,
                validPreset
            );
        }

        presetSelect.value = validPreset;

        applyColumnVisibility(
            context,
            visibleColumns,
            false
        );

        const storedSort = readStorage(
            SORT_STORAGE_KEY,
            {
                column: "考勤排序等级",
                direction: "asc"
            }
        );

        const sortState = (
            storedSort
            && typeof storedSort.column === "string"
            && (
                storedSort.direction === "asc"
                || storedSort.direction === "desc"
            )
        )
            ? storedSort
            : {
                column: "考勤排序等级",
                direction: "asc"
            };

        applySort(
            context,
            sortState,
            false
        );

        applyStatusFilter(
            context,
            "all"
        );

        headers.forEach(
            (header) => {
                const button = header.querySelector(
                    "[data-ca-sort-column]"
                );

                if (!button) {
                    return;
                }

                button.addEventListener(
                    "click",
                    () => {
                        const column = (
                            button.dataset.caSortColumn
                        );

                        const direction = (
                            context.sortState
                            && context.sortState.column
                            === column
                            && context.sortState.direction
                            === "asc"
                        )
                            ? "desc"
                            : "asc";

                        applySort(
                            context,
                            {
                                column,
                                direction
                            },
                            true
                        );
                    }
                );
            }
        );

        presetSelect.addEventListener(
            "change",
            () => {
                const presetName = presetSelect.value;

                if (presetName === "custom") {
                    return;
                }

                const columns = columnsForPreset(
                    table,
                    presetName
                );

                applyColumnVisibility(
                    context,
                    columns,
                    false
                );

                writeStorage(
                    PRESET_STORAGE_KEY,
                    presetName
                );

                writeStorage(
                    COLUMN_STORAGE_KEY,
                    columns
                );
            }
        );

        filterButtons.forEach(
            (button) => {
                button.addEventListener(
                    "click",
                    () => {
                        applyStatusFilter(
                            context,
                            button.dataset.caStatusFilter
                        );
                    }
                );
            }
        );

        const exportButtons = toolbar.querySelectorAll(
            "[data-ca-export-mode]"
        );

        exportButtons.forEach(
            (button) => {
                button.addEventListener(
                    "click",
                    () => {
                        const menu = button.closest("details");

                        if (menu) {
                            menu.open = false;
                        }

                        exportExcel(
                            context,
                            button.dataset.caExportMode
                                || "smart_report",
                            button
                        );
                    }
                );
            }
        );

        const resetButton = toolbar.querySelector(
            "[data-ca-reset-table]"
        );

        if (resetButton) {
            resetButton.addEventListener(
                "click",
                () => resetTable(context)
            );
        }
    }

    document.addEventListener(
        "DOMContentLoaded",
        () => {
            const dashboard = document.querySelector(
                "[data-ca-dashboard]"
            );

            if (dashboard) {
                initialiseGroupPanel(dashboard);
            }

            initialiseMemberTable();
        }
    );

    function initialiseAttendanceConfigurationForm() {
        const editor = document.querySelector(
            "[data-attendance-config-form]"
        );

        if (!editor) {
            return;
        }

        const form = editor.closest("form");

        if (!form) {
            return;
        }

        const metricEditors = Array.from(
            editor.querySelectorAll(
                "[data-attendance-metric]"
            )
        );

        const statusElement = editor.querySelector(
            "[data-attendance-config-status]"
        );

        function readMetric(editorElement) {
            const code = editorElement.getAttribute(
                "data-attendance-metric"
            );

            const enableInput = editorElement.querySelector(
                "[data-attendance-enable]"
            );

            const weightInput = editorElement.querySelector(
                "[data-attendance-weight]"
            );

            const preview = editor.querySelector(
                `[data-attendance-weight-preview="${code}"]`
            );

            const parsedWeight = Number(
                weightInput ? weightInput.value : 0
            );

            return {
                code,
                enabled: Boolean(
                    enableInput && enableInput.checked
                ),
                weight: Number.isFinite(parsedWeight)
                    ? Math.max(parsedWeight, 0)
                    : 0,
                preview,
            };
        }

        function updateWeightPreview() {
            const metrics = metricEditors.map(
                readMetric
            );

            const enabledMetrics = metrics.filter(
                (metric) => metric.enabled
            );

            const totalWeight = enabledMetrics.reduce(
                (total, metric) => (
                    total + metric.weight
                ),
                0
            );

            metrics.forEach((metric) => {
                if (!metric.preview) {
                    return;
                }

                if (!metric.enabled) {
                    metric.preview.textContent = "未纳入";
                    return;
                }

                if (totalWeight <= 0) {
                    metric.preview.textContent = "待设置";
                    return;
                }

                const percentage = (
                    metric.weight
                    / totalWeight
                    * 100
                );

                metric.preview.textContent = (
                    percentage.toFixed(1)
                    + "%"
                );
            });

            if (!statusElement) {
                return;
            }

            if (enabledMetrics.length === 0) {
                statusElement.textContent = (
                    "至少启用一项指标"
                );
                return;
            }

            if (totalWeight <= 0) {
                statusElement.textContent = (
                    "启用指标权重必须大于0"
                );
                return;
            }

            statusElement.textContent = (
                "已启用"
                + enabledMetrics.length
                + "项，权重自动归一化"
            );
        }

        metricEditors.forEach((metricEditor) => {
            metricEditor.addEventListener(
                "input",
                updateWeightPreview
            );

            metricEditor.addEventListener(
                "change",
                updateWeightPreview
            );
        });

        form.addEventListener(
            "submit",
            (event) => {
                const metrics = metricEditors.map(
                    readMetric
                );

                const enabledMetrics = metrics.filter(
                    (metric) => metric.enabled
                );

                if (enabledMetrics.length === 0) {
                    event.preventDefault();

                    window.alert(
                        "至少启用一项考勤指标。"
                    );

                    return;
                }

                const enabledWeightTotal = (
                    enabledMetrics.reduce(
                        (total, metric) => (
                            total + metric.weight
                        ),
                        0
                    )
                );

                if (enabledWeightTotal <= 0) {
                    event.preventDefault();

                    window.alert(
                        "已启用指标的权重总和必须大于0。"
                    );
                }
            }
        );

        updateWeightPreview();
    }

    document.addEventListener(
        "DOMContentLoaded",
        initialiseAttendanceConfigurationForm
    );
})();


/* A15.4.30-A4-B1 多范围驾驶舱选择器 */
(function () {
    "use strict";

    function parseScopeOptions() {
        const source = document.getElementById(
            "compare-scope-options"
        );

        if (!source) {
            return {
                group: [],
                member: []
            };
        }

        try {
            const parsed = JSON.parse(
                source.textContent || "{}"
            );

            return {
                group: Array.isArray(
                    parsed.group
                )
                    ? parsed.group
                    : [],
                member: Array.isArray(
                    parsed.member
                )
                    ? parsed.member
                    : []
            };
        } catch (error) {
            console.error(
                "分析范围选项解析失败",
                error
            );

            return {
                group: [],
                member: []
            };
        }
    }

    function addOption(
        select,
        value,
        label,
        selectedValue
    ) {
        const option = document.createElement(
            "option"
        );

        option.value = String(value);
        option.textContent = String(label);

        if (
            String(value)
            === String(selectedValue)
        ) {
            option.selected = true;
        }

        select.appendChild(option);
    }

    function initialiseCompareScopeSelector() {
        const typeSelect =
            document.getElementById(
                "analysis-scope-type"
            );

        const valueSelect =
            document.getElementById(
                "analysis-scope-value"
            );

        const valueLabel =
            document.getElementById(
                "analysis-scope-value-label"
            );

        if (
            !typeSelect
            || !valueSelect
            || !valueLabel
        ) {
            return;
        }

        const options = parseScopeOptions();

        function renderValueOptions(
            preserveCurrentValue
        ) {
            const scopeType =
                typeSelect.value
                || "alliance";

            const currentValue =
                preserveCurrentValue
                    ? (
                        valueSelect.dataset
                            .currentValue
                        || valueSelect.value
                        || ""
                    )
                    : "";

            valueSelect.innerHTML = "";
            valueSelect.setCustomValidity("");

            if (scopeType === "alliance") {
                valueLabel.textContent =
                    "范围对象";

                valueSelect.disabled = true;
                valueSelect.required = false;

                addOption(
                    valueSelect,
                    "",
                    "全同盟，无需选择",
                    ""
                );

                return;
            }

            valueSelect.disabled = false;
            valueSelect.required = true;

            const values =
                scopeType === "group"
                    ? options.group
                    : options.member;

            valueLabel.textContent =
                scopeType === "group"
                    ? "选择分组"
                    : "选择成员";

            if (!values.length) {
                addOption(
                    valueSelect,
                    "",
                    scopeType === "group"
                        ? "暂无可选分组"
                        : "暂无可选成员",
                    ""
                );

                valueSelect.setCustomValidity(
                    scopeType === "group"
                        ? "当前结束快照没有可选分组。"
                        : "当前结束快照没有可选成员。"
                );

                return;
            }

            addOption(
                valueSelect,
                "",
                scopeType === "group"
                    ? "请选择分组"
                    : "请选择成员",
                currentValue
            );

            values.forEach(
                function (value) {
                    addOption(
                        valueSelect,
                        value,
                        value,
                        currentValue
                    );
                }
            );
        }

        typeSelect.addEventListener(
            "change",
            function () {
                valueSelect.dataset.currentValue =
                    "";

                renderValueOptions(false);
            }
        );

        valueSelect.addEventListener(
            "change",
            function () {
                valueSelect.dataset.currentValue =
                    valueSelect.value;

                valueSelect.setCustomValidity("");
            }
        );

        const form = typeSelect.closest(
            "form"
        );

        if (form) {
            form.addEventListener(
                "submit",
                function (event) {
                    if (
                        typeSelect.value
                        !== "alliance"
                        && !valueSelect.value
                    ) {
                        valueSelect.setCustomValidity(
                            typeSelect.value
                            === "group"
                                ? "请选择一个分组。"
                                : "请选择一个成员。"
                        );

                        valueSelect.reportValidity();
                        event.preventDefault();
                    }
                }
            );
        }

        renderValueOptions(true);
    }

    document.addEventListener(
        "DOMContentLoaded",
        initialiseCompareScopeSelector
    );
})();
