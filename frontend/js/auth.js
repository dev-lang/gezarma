const auth = {
    getUser() {
        // We store user info separately for must_change_password etc.
        const info = localStorage.getItem("user_info");
        if (info) {
            try { return JSON.parse(info); } catch {}
        }
        // Fallback: decode JWT
        const token = localStorage.getItem("token");
        if (!token) return null;
        try {
            const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
            const json   = decodeURIComponent(atob(base64).split("").map(c =>
                "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)
            ).join(""));
            return JSON.parse(json);
        } catch { this.logout(); return null; }
    },

    isLoggedIn() { return !!localStorage.getItem("token"); },

    setSession(data) {
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("user_info", JSON.stringify({
            username:            data.username,
            role:                data.role,
            nombre:              data.nombre,
            user_id:             data.user_id,
            must_change_password: data.must_change_password || false,
        }));
    },

    logout() {
        if (window.Notif) window.Notif.stop();
        localStorage.removeItem("token");
        localStorage.removeItem("user_info");
        window.location.reload();
    },

    checkAuth() {
        if (!this.isLoggedIn()) {
            ui.showSection("login");
        } else {
            const user = this.getUser();
            if (user && user.must_change_password) {
                ui.showSection("change-password");
            } else {
                ui.initDashboard();
                // Start polling (deferred so modules have loaded)
                setTimeout(() => { if (window.Notif) window.Notif.init(); }, 500);
            }
        }
    },
};
