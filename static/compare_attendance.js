(() => {
    "use strict";

    const STORAGE_KEY = "compareAttendanceGroupsExpandedV1";

    function readExpandedState() {
        try {
            const value = window.localStorage.getItem(STORAGE_KEY);

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

    function saveExpandedState(expanded) {
        try {
            window.localStorage.setItem(
                STORAGE_KEY,
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
                saveExpandedState(expanded);
            }
        };

        updateState(
            readExpandedState(),
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

    document.addEventListener(
        "DOMContentLoaded",
        () => {
            const dashboard = document.querySelector(
                "[data-ca-dashboard]"
            );

            if (!dashboard) {
                return;
            }

            initialiseGroupPanel(dashboard);
        }
    );
})();
