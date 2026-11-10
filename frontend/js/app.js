/**
 * app.js — Application entry point.
 * bindEvents() is called every time a new partial is injected into the DOM.
 * All handlers use optional chaining (?.) so missing elements are safe.
 */
const app = {
    currentPage: 0,
    pageSize: 50,
    _eventsController: null,   // AbortController — cancels ALL listeners on re-bind

    init() {
        auth.checkAuth();
    },

    // Called after every partial load.
    // AbortController ensures old listeners are removed before adding new ones,
    // preventing the N-submissions-per-click bug when modals persist in <body>.
    bindEvents() {
        if (this._eventsController) this._eventsController.abort();
        this._eventsController = new AbortController();
        const sig = { signal: this._eventsController.signal };
        window.Barra?.pintarMarca();      // nombre y logo del taller en la pantalla nueva (ingreso)

        // Selectores de idioma (barra superior, login y registro)
        document.querySelectorAll('[data-idioma-selector]:empty').forEach(el =>
            el.appendChild(I18N.selector(el.dataset.idiomaSelector || '')));

        const on = (id, event, handler) => {
            document.getElementById(id)?.addEventListener(event, handler, sig);
        };
        const onAll = (selector, event, handler) => {
            document.querySelectorAll(selector).forEach(el => el.addEventListener(event, handler, sig));
        };
        // ── Auth ──────────────────────────────────────────────────────────
        on('to-register', 'click', e => { e.preventDefault(); ui.showSection('register'); });
        on('to-login', 'click', e => { e.preventDefault(); ui.showSection('login'); });
        on('logout-btn', 'click', () => auth.logout());
        on('dark-toggle',  'click', () => ui.toggleDark());
        on('back-to-list', 'click', () => ui.initDashboard());

        // ── Change password (forced after admin reset) ─────────────────────
        on('cp-submit-btn', 'click', async () => {
            const currentPw = document.getElementById('cp-current-password')?.value || '';
            const newPw     = document.getElementById('cp-new-password')?.value || '';
            const confirmPw = document.getElementById('cp-confirm-password')?.value || '';
            const errEl     = document.getElementById('cp-error');
            const btn       = document.getElementById('cp-submit-btn');

            const showErr = msg => {
                if (errEl) { errEl.textContent = msg; errEl.classList.remove('hidden'); }
                else toast.error(msg);
            };
            if (errEl) errEl.classList.add('hidden');

            if (!currentPw)              { showErr('Ingresá tu contraseña actual.'); return; }
            if (newPw.length < 6)        { showErr('La contraseña debe tener al menos 6 caracteres.'); return; }
            if (newPw !== confirmPw)      { showErr('Las contraseñas no coinciden.'); return; }

            try {
                if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }
                const res = await api.changePassword(currentPw, newPw);
                // Al cambiar la clave el servidor invalida los tokens anteriores y manda uno nuevo
                if (res?.access_token) localStorage.setItem('token', res.access_token);
                // Update local session so must_change_password is cleared
                const user = auth.getUser();
                if (user) {
                    user.must_change_password = false;
                    localStorage.setItem('user_info', JSON.stringify(user));
                }
                toast.success('Contraseña actualizada correctamente.');
                ui.initDashboard();
                if (window.Notif) window.Notif.init();
            } catch(err) {
                showErr(err.message || 'Error al cambiar la contraseña.');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = 'Establecer nueva contraseña'; }
            }
        });

        // Allow Enter key on confirm field to submit
        document.getElementById('cp-confirm-password')?.addEventListener('keydown', e => {
            if (e.key === 'Enter') document.getElementById('cp-submit-btn')?.click();
        }, sig);

        // ── Login ─────────────────────────────────────────────────────────
        on('login-form', 'submit', async e => {
            e.preventDefault();
            const userEl = document.getElementById('login-username');
            const passEl = document.getElementById('login-password');
            const errBanner = document.getElementById('login-error');
            const errMsg    = document.getElementById('login-error-msg');
            const userErr   = document.getElementById('login-username-err');
            const passErr   = document.getElementById('login-password-err');

            // Reset errors
            [userErr, passErr, errBanner].forEach(el => el?.classList.add('hidden'));

            let valid = true;
            if (!userEl?.value.trim()) { userErr?.classList.remove('hidden'); valid = false; }
            if (!passEl?.value)        { passErr?.classList.remove('hidden'); valid = false; }
            if (!valid) return;

            ui.setLoading('login-form-btn', true);
            try {
                const res = await api.login(userEl.value.trim(), passEl.value);
                auth.setSession(res);
                if (I18N.deLaCuenta(res.idioma)) return;   // la cuenta tiene otro idioma: recarga en ese
                if (res.must_change_password) {
                    ui.showSection('change-password');
                } else {
                    ui.initDashboard();
                    // Start notification polling
                    if (window.Notif) { window.Notif.init(); }
                }
            } catch (err) {
                if (errBanner && errMsg) {
                    errMsg.textContent = err.message;
                    errBanner.classList.remove('hidden');
                    userEl?.classList.add('border-red-400');
                    passEl?.classList.add('border-red-400');
                }
            } finally {
                ui.setLoading('login-form-btn', false);
            }
        });

        // Clear red borders on input
        on('login-username', 'input', () => {
            document.getElementById('login-username')?.classList.remove('border-red-400');
            document.getElementById('login-error')?.classList.add('hidden');
            document.getElementById('login-username-err')?.classList.add('hidden');
        });
        on('login-password', 'input', () => {
            document.getElementById('login-password')?.classList.remove('border-red-400');
            document.getElementById('login-error')?.classList.add('hidden');
            document.getElementById('login-password-err')?.classList.add('hidden');
        });

        // Password show/hide toggle
        on('toggle-password', 'click', () => {
            const input = document.getElementById('login-password');
            if (!input) return;
            input.type = input.type === 'password' ? 'text' : 'password';
            const icon = document.getElementById('eye-icon');
            if (icon) icon.style.opacity = input.type === 'text' ? '0.5' : '1';
        });

        // ── Register ──────────────────────────────────────────────────────
        on('register-form', 'submit', async e => {
            e.preventDefault();
            const nombre   = document.getElementById('reg-nombre').value.trim();
            const username = document.getElementById('reg-username').value.trim();
            const email    = document.getElementById('reg-email').value.trim();
            const password = document.getElementById('reg-password').value;

            if (!nombre || !username || !email || !password) {
                toast.error('Todos los campos son obligatorios.');
                return;
            }
            if (password.length < 6) {
                toast.error('La contraseña debe tener al menos 6 caracteres.');
                return;
            }
            if (!/^[a-zA-Z0-9._@+\-]+$/.test(username)) {
                toast.error('El nombre de usuario solo puede contener letras, números y . _ @ + -');
                return;
            }

            const data = {
                nombre,
                username,
                email,
                tipo_cliente: document.getElementById('reg-tipo').value,
                password,
                idioma: I18N.codigo,
            };
            try {
                await api.register(data);
                toast.success('Registro exitoso. Ya podés iniciar sesión.');
                ui.showSection('login');
            } catch (err) {
                toast.error(err.message);
            }
        });

        // ── Dashboard: admin navigation ───────────────────────────────────
        on('favorites-nav-btn',   'click', () => ui.initFavorites());

        // ── Admin panel ────────────────────────────────────────────────────
        on('back-to-dashboard-from-admin', 'click', () => ui.initDashboard());

        // Tab switching
        document.querySelectorAll('.admin-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => ui.adminSwitchTab(btn.dataset.tab), sig);
        });

        // Users tab filters
        on('admin-user-filter-rol',    'change', () => ui.adminRenderUsers());
        on('admin-user-filter-activo', 'change', () => ui.adminRenderUsers());

        // Products tab
        on('admin-new-product-btn',      'click',  () => ui.openNewProductForm());
        on('admin-import-products-btn',  'click',  () => Importar.abrir('productos', () => ui.loadAdminPanel('products')));
        on('admin-import-parts-btn',     'click',  () => Importar.abrir('repuestos', () => ui.loadAdminPanel('parts')));
        on('import-parts-btn',           'click',  () => Importar.abrir('repuestos', () => ui.loadPartsManagement()));
        document.getElementById('import-parts-btn')?.classList.toggle('hidden', auth.getUser()?.role !== 'administrador');
        on('admin-product-search',       'input',  () => ui.adminRenderProducts());
        on('admin-product-filter-cat',   'change', () => ui.adminRenderProducts());

        // Parts tab
        on('admin-new-part-btn',  'click', () => {
            // Reset form for new part
            ['part-form-id','part-form-nombre','part-form-codigo','part-form-proveedor'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            const s = document.getElementById('part-form-stock');   if (s) s.value = '0';
            const pr = document.getElementById('part-form-precio');  if (pr) pr.value = '0';
            const sm = document.getElementById('part-form-stock-minimo'); if (sm) sm.value = '0';
            document.getElementById('part-form-title').textContent = 'Nuevo Repuesto';
            if (typeof Ubic !== 'undefined') Ubic.llenarSelect('part-form-ubicacion', null);
            document.getElementById('parts-form-modal').classList.remove('hidden');
        });
        on('admin-parts-search',  'input', () => ui.adminRenderParts());

        // New user from admin
        on('admin-new-user-btn', 'click', () => {
            ['nu-username','nu-nombre','nu-email','nu-password'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            document.getElementById('nu-rol').value  = 'cliente';
            document.getElementById('nu-tipo').value = 'persona';
            document.getElementById('new-user-modal').classList.remove('hidden');
            document.getElementById('nu-username').focus();
        });
        on('close-new-user-modal', 'click', () => document.getElementById('new-user-modal').classList.add('hidden'));
        on('cancel-new-user',      'click', () => document.getElementById('new-user-modal').classList.add('hidden'));
        document.getElementById('new-user-modal')?.addEventListener('click', e => {
            if (e.target.id === 'new-user-modal') e.target.classList.add('hidden');
        });
        on('new-user-form', 'submit', async e => {
            e.preventDefault();
            const data = {
                username:     document.getElementById('nu-username').value.trim(),
                password:     document.getElementById('nu-password').value,
                nombre:       document.getElementById('nu-nombre').value.trim(),
                email:        document.getElementById('nu-email').value.trim(),
                rol:          document.getElementById('nu-rol').value,
                tipo_cliente: document.getElementById('nu-tipo').value,
            };
            if (!data.username || !data.password || !data.nombre || !data.email) {
                toast.warning('Completá todos los campos obligatorios.'); return;
            }
            if (data.password.length < 6) {
                toast.warning('La contraseña debe tener al menos 6 caracteres.'); return;
            }
            try {
                ui.setLoading('create-user-btn', true);
                await api.register(data);
                document.getElementById('new-user-modal').classList.add('hidden');
                toast.success(`Usuario "${data.username}" creado correctamente.`);
                const updated = await api.getUsers();
                ui._adminUsersCache = updated;
                document.getElementById('admin-user-count').textContent = updated.length;
                ui.adminRenderUsers();
            } catch(err) {
                toast.error(err.message);
            } finally {
                ui.setLoading('create-user-btn', false);
            }
        });

        // Tags tab
        on('admin-new-tag-btn', 'click', () => {
            document.getElementById('tag-form-id').value     = '';
            document.getElementById('tag-form-nombre').value = '';
            document.getElementById('tag-form-color').value  = '#3b82f6';
            document.getElementById('tag-form-container').classList.remove('hidden');
            document.getElementById('tag-form-nombre').focus();
        });
        on('tag-form-cancel', 'click', () => document.getElementById('tag-form-container').classList.add('hidden'));
        on('tag-form-save',   'click', async () => {
            const id     = document.getElementById('tag-form-id').value;
            const nombre = document.getElementById('tag-form-nombre').value.trim();
            const color  = document.getElementById('tag-form-color').value;
            if (!nombre) { toast.warning('Ingresá un nombre.'); return; }
            try {
                if (id) { await api.updateTag(parseInt(id), { nombre, color }); toast.success('Etiqueta actualizada.'); }
                else    { await api.createTag({ nombre, color }); toast.success('Etiqueta creada.'); }
                document.getElementById('tag-form-container').classList.add('hidden');
                await ui.loadAdminTags();
            } catch(err) { toast.error(err.message); }
        });

        // Plantillas tab
        on('admin-new-plantilla-btn', 'click', () => {
            ['plantilla-form-id','plantilla-form-nombre','plantilla-form-texto'].forEach(id => {
                const el = document.getElementById(id); if (el) el.value = '';
            });
            document.getElementById('plantilla-form-orden').value = '0';
            document.getElementById('plantilla-form-container').classList.remove('hidden');
            document.getElementById('plantilla-form-nombre').focus();
        });
        on('plantilla-form-cancel', 'click', () => document.getElementById('plantilla-form-container').classList.add('hidden'));
        on('plantilla-form-save',   'click', async () => {
            const id     = document.getElementById('plantilla-form-id').value;
            const nombre = document.getElementById('plantilla-form-nombre').value.trim();
            const texto  = document.getElementById('plantilla-form-texto').value.trim();
            const orden  = parseInt(document.getElementById('plantilla-form-orden').value) || 0;
            if (!nombre || !texto) { toast.warning('Completá nombre y texto.'); return; }
            try {
                if (id) await api.updatePlantilla(parseInt(id), { nombre, texto, orden });
                else    await api.createPlantilla({ nombre, texto, orden });
                document.getElementById('plantilla-form-container').classList.add('hidden');
                await ui.loadAdminPlantillas();
                toast.success(id ? 'Plantilla actualizada.' : 'Plantilla creada.');
            } catch(err) { toast.error(err.message); }
        });

        // Estados tab
        on('admin-new-estado-btn', 'click', () => {
            ['estado-form-id','estado-form-valor','estado-form-etiqueta'].forEach(id => {
                const el = document.getElementById(id); if (el) el.value = '';
            });
            document.getElementById('estado-form-color').value  = '#6b7280';
            document.getElementById('estado-form-orden').value  = '0';
            document.getElementById('estado-form-activo').checked = true;
            document.getElementById('estado-form-final').checked  = false;
            document.getElementById('estado-form-container').classList.remove('hidden');
            document.getElementById('estado-form-valor').focus();
        });
        on('estado-form-cancel', 'click', () => document.getElementById('estado-form-container').classList.add('hidden'));
        on('estado-form-save',   'click', async () => {
            const id       = document.getElementById('estado-form-id').value;
            const valor    = document.getElementById('estado-form-valor').value.trim();
            const etiqueta = document.getElementById('estado-form-etiqueta').value.trim();
            const color    = document.getElementById('estado-form-color').value;
            const orden    = parseInt(document.getElementById('estado-form-orden').value) || 0;
            const activo   = document.getElementById('estado-form-activo').checked;
            const es_final = document.getElementById('estado-form-final').checked;
            if (!valor || !etiqueta) { toast.warning('Completá valor y etiqueta.'); return; }
            try {
                if (id) await api.updateEstado(parseInt(id), { valor, etiqueta, color, orden, activo, es_final });
                else    await api.createEstado({ valor, etiqueta, color, orden, activo, es_final });
                document.getElementById('estado-form-container').classList.add('hidden');
                await ui.loadAdminEstados();
                toast.success(id ? 'Estado actualizado.' : 'Estado creado.');
            } catch(err) { toast.error(err.message); }
        });

        // Stock tab
        on('admin-reposicion-btn',    'click', () => app.openReposicionModal());
        on('close-reposicion-modal',  'click', () => document.getElementById('reposicion-modal')?.classList.add('hidden'));
        on('cancel-reposicion',       'click', () => document.getElementById('reposicion-modal')?.classList.add('hidden'));
        on('confirm-reposicion-btn',  'click', () => app.confirmarReposicion());
        on('admin-stock-refresh-btn', 'click', async () => {
            const v = document.getElementById('admin-stock-filter-part')?.value;
            await ui.loadStockHistory(v ? parseInt(v) : null);
        });
        on('admin-stock-filter-cat', 'change', async () => {
            // When category changes, also reset part filter to match
            await ui.loadStockHistory();
        });
        on('admin-stock-filter-part', 'change', async e => {
            await ui.loadStockHistory(e.target.value ? parseInt(e.target.value) : null);
        });

        // ── Users page (standalone, legacy) ───────────────────────────────
        on('back-to-dashboard-from-users', 'click', () => ui.initDashboard());
        on('user-filter-rol', 'change', () => ui.renderUsers());
        on('user-filter-activo', 'change', () => ui.renderUsers());

        // ── User edit modal ────────────────────────────────────────────────
        on('close-user-modal', 'click', () => document.getElementById('user-edit-modal')?.classList.add('hidden'));
        on('cancel-user-edit', 'click', () => document.getElementById('user-edit-modal')?.classList.add('hidden'));

        onAll('input[name="user-rol"]', 'change', e => ui._updateRolDescription(e.target.value));

        on('toggle-activo-btn', 'click', () => {
            ui._userEditActivo = !ui._userEditActivo;
            ui._updateActivoToggle();
        });

        on('user-edit-form', 'submit', async e => {
            e.preventDefault();
            const id     = document.getElementById('user-edit-id').value;
            const rol    = document.querySelector('input[name="user-rol"]:checked')?.value;
            const nombre    = document.getElementById('user-edit-nombre')?.value.trim();
            const email     = document.getElementById('user-edit-email')?.value.trim();
            const telefono  = document.getElementById('user-edit-telefono')?.value.trim();
            const data      = { rol, activo: ui._userEditActivo };
            try {
                ui.setLoading('save-user-btn', true);
                await api.updateUser(id, data);
                if (nombre || email || telefono !== undefined) {
                    const profileData = {};
                    if (nombre)   profileData.nombre   = nombre;
                    if (email)    profileData.email    = email;
                    if (telefono !== undefined) profileData.telefono = telefono || null;
                    await api.updateUserProfile(id, profileData);
                }
                document.getElementById('user-edit-modal')?.classList.add('hidden');
                document.getElementById('temp-pw-display')?.classList.add('hidden');
                toast.success('Usuario actualizado correctamente.');
                if (document.getElementById('admin-section')) {
                    const updated = await api.getUsers();
                    ui._adminUsersCache = updated;
                    document.getElementById('admin-user-count').textContent = updated.length;
                    ui.adminRenderUsers();
                } else { ui.loadUsers(); }
            } catch (err) {
                toast.error(err.message);
            } finally {
                ui.setLoading('save-user-btn', false);
            }
        });

        // Reset password
        on('reset-pw-btn', 'click', async () => {
            const id = document.getElementById('user-edit-id')?.value;
            if (!id) return;
            const ok = await confirmDialog('¿Blanquear contraseña?',
                'Se generará una clave temporal. El usuario deberá cambiarla en el próximo login.');
            if (!ok) return;
            try {
                const res = await api.resetPassword(parseInt(id));
                document.getElementById('temp-pw-value').textContent = res.temp_password;
                document.getElementById('temp-pw-display').classList.remove('hidden');
                toast.success('Contraseña reseteada. Copiala antes de cerrar.');
            } catch(err) { toast.error(err.message); }
        });
        on('copy-temp-pw', 'click', () => {
            const val = document.getElementById('temp-pw-value')?.textContent;
            if (val) { navigator.clipboard.writeText(val); toast.success('Copiada al portapapeles.'); }
        });

        // ── Products page ──────────────────────────────────────────────────
        on('back-to-dashboard-from-products', 'click', () => ui.initDashboard());
        on('new-product-btn', 'click', () => ui.openNewProductForm());
        on('close-product-modal', 'click', () => document.getElementById('product-form-modal')?.classList.add('hidden'));
        on('cancel-product-form', 'click', () => document.getElementById('product-form-modal')?.classList.add('hidden'));
        on('product-search-input', 'input', () => ui.filterProducts());
        on('product-filter-categoria', 'change', () => ui.filterProducts());

        on('product-form', 'submit', async e => {
            e.preventDefault();
            const id   = document.getElementById('product-form-id').value;
            const data = {
                marca:                    document.getElementById('product-form-marca').value.trim(),
                modelo:                   document.getElementById('product-form-modelo').value.trim(),
                categoria:                document.getElementById('product-form-categoria').value.trim(),
                periodo_garantia_meses:   parseInt(document.getElementById('product-form-garantia').value),
                numero_parte:             document.getElementById('product-form-nroparte').value.trim() || null,
            };
            try {
                ui.setLoading('product-form-btn', true);
                id ? await api.updateProduct(id, data) : await api.createProduct(data);
                document.getElementById('product-form-modal')?.classList.add('hidden');
                toast.success(id ? 'Producto actualizado.' : 'Producto creado correctamente.');
                // Refresh whichever view is active
                if (document.getElementById('admin-section')) {
                    const updated = await api.getProducts();
                    ui._adminProductsCache = updated;
                    document.getElementById('admin-product-count').textContent = updated.length;
                    ui.adminBuildProductCats();
                    ui.adminRenderProducts();
                } else { ui.loadProducts(); }
            } catch (err) {
                toast.error(err.message);
            } finally {
                ui.setLoading('product-form-btn', false);
            }
        });

        // ── Parts page ────────────────────────────────────────────────────
        on('back-to-dashboard-from-parts', 'click', () => ui.initDashboard());
        on('new-part-btn', 'click', () => ui.openNewPartForm());
        on('close-part-modal', 'click', () => document.getElementById('parts-form-modal')?.classList.add('hidden'));

        // ── Parts form ────────────────────────────────────────────────────
        on('part-form', 'submit', async e => {
            e.preventDefault();
            const id   = document.getElementById('part-form-id').value;
            const data = {
                nombre:     document.getElementById('part-form-nombre').value,
                codigo:     document.getElementById('part-form-codigo').value,
                proveedor:  document.getElementById('part-form-proveedor').value,
                stock:      parseInt(document.getElementById('part-form-stock').value),
                precio:     parseFloat(document.getElementById('part-form-precio').value),
                stock_minimo: parseInt(document.getElementById('part-form-stock-minimo')?.value || '0') || 0,
                categoria:  document.getElementById('part-form-categoria')?.value || 'General',
            };
            const ubicSel = document.getElementById('part-form-ubicacion');
            if (ubicSel && ubicSel.options.length > 1) data.ubicacion_id = Number(ubicSel.value) || null;
            try {
                ui.setLoading('part-form-btn', true);
                id ? await api.updatePart(id, data) : await api.createPart(data);
                document.getElementById('parts-form-modal')?.classList.add('hidden');
                toast.success(id ? 'Repuesto actualizado.' : 'Repuesto creado correctamente.');
                if (document.getElementById('admin-section')) {
                    const updated = await api.getParts();
                    ui._adminPartsCache = updated;
                    document.getElementById('admin-parts-count').textContent = updated.length;
                    ui.adminRenderParts();
                    ui.adminCheckStockAlerts(updated);
                } else { ui.loadPartsManagement(); }
            } catch (err) {
                toast.error(err.message);
            } finally {
                ui.setLoading('part-form-btn', false);
            }
        });

        // ── "Limpiar filtros" desde un estado vacío ──────────────────────────
        document.addEventListener('vacio:limpiar', e => {
            const en = id => e.target.closest(`#${id}`);
            const vaciar = ids => ids.forEach(id => { const c = document.getElementById(id); if (c) c.value = ''; });
            if (en('ticket-list-body'))        ui.loadTickets({ status: '' });
            if (en('product-list-body'))       { vaciar(['product-search-input', 'product-filter-categoria']); ui.filterProducts(); }
            if (en('admin-product-list-body')) { vaciar(['admin-product-search', 'admin-product-filter-cat']); ui.adminRenderProducts(); }
            if (en('admin-user-list-body'))    { vaciar(['admin-user-filter-rol', 'admin-user-filter-activo']); ui.adminRenderUsers(); }
            if (en('user-list-body'))          { vaciar(['user-filter-rol', 'user-filter-activo']); ui.renderUsers(); }
        }, sig);

        // ── Filters ───────────────────────────────────────────────────────

        // ── Ticket modal ──────────────────────────────────────────────────
        on('mostrador-btn', 'click', () => Recepcion.abrirMostrador());
        on('horas-btn', 'click', () => Horas.abrir());
        on('externos-btn', 'click', () => Envios.abrir());
        on('create-ticket-btn', 'click', () => {
            ui.loadProductsSelect();
            // La prioridad la decide el taller: para el cliente se calcula sola
            document.getElementById('tk-prioridad-wrap')?.classList.toggle('hidden', (auth.getUser()?.role || '') === 'cliente');
            document.getElementById('ticket-modal')?.classList.remove('hidden');
        });
        on('close-modal',    'click', () => app.confirmModalClose('ticket-modal'));
        on('cancel-ticket',  'click', () => app.confirmModalClose('ticket-modal'));
        app._modalDirty = false;
        app.trackModalDirty('ticket-form');
        document.getElementById('ticket-modal')?.addEventListener('click', e => {
            if (e.target.id === 'ticket-modal') app.confirmModalClose('ticket-modal');
        }, sig);
        document.getElementById('product-form-modal')?.addEventListener('click', e => {
            if (e.target.id === 'product-form-modal') e.target.classList.add('hidden');
        }, sig);
        document.getElementById('parts-form-modal')?.addEventListener('click', e => {
            if (e.target.id === 'parts-form-modal') e.target.classList.add('hidden');
        }, sig);
        document.getElementById('user-edit-modal')?.addEventListener('click', e => {
            if (e.target.id === 'user-edit-modal') e.target.classList.add('hidden');
        }, sig);

        on('ticket-form', 'submit', async e => {
            e.preventDefault();
            const productSelect = document.getElementById('tk-producto-id');
            const fechaCompraVal = document.getElementById('tk-compra').value;
            if (fechaCompraVal && new Date(fechaCompraVal) > new Date()) {
                toast.error('La fecha de compra no puede ser una fecha futura.');
                return;
            }
            const data = {
                producto_id: parseInt(productSelect.value),
                producto:    productSelect.options[productSelect.selectedIndex].text,
                numero_serie:document.getElementById('tk-serie').value,
                fecha_compra:new Date(fechaCompraVal).toISOString(),
                prioridad:   document.getElementById('tk-prioridad').value,
                descripcion: document.getElementById('tk-descripcion').value,
            };
            ui.setLoading('ticket-form-btn', true);
            try {
                await api.createTicket(data);
                document.getElementById('ticket-modal')?.classList.add('hidden');
                toast.success('Ticket creado correctamente.');
                app._modalDirty = false;
                ui.initDashboard();
                e.target.reset();
            } catch (err) {
                toast.error(err.message);
            } finally {
                ui.setLoading('ticket-form-btn', false);
            }
        });

        // ── Detail: tabs ──────────────────────────────────────────────────
        on('tab-comments', 'click', () => ui.switchTab('comments'));
        on('tab-history', 'click', () => ui.switchTab('history'));

        // ── Internal note toggle ─────────────────────────────────────────────
        const _user = auth.getUser();
        if (_user && _user.role !== 'cliente') {
            document.getElementById('internal-note-row')?.classList.replace('hidden','flex');
        }

        // ── Detail: comment ───────────────────────────────────────────────
        on('add-comment-btn', 'click', async () => {
            const text = document.getElementById('new-comment').value.trim();
            if (!text) { toast.warning('Escribí un comentario antes de enviar.'); return; }
            const isInternal = document.getElementById('is-internal-toggle')?.checked || false;
            try {
                await api.addComment(ui.currentTicketId, text, isInternal);
                document.getElementById('new-comment').value = '';
                const tog = document.getElementById('is-internal-toggle');
                if (tog) tog.checked = false;
                ui.loadComments(ui.currentTicketId);
                toast.success(isInternal ? 'Nota interna guardada.' : 'Comentario enviado.');
            } catch (err) { toast.error(err.message); }
        });

        // ── Detail: status toggle → show shipping fields ──────────────────


        // ── Edit fields card ──────────────────────────────────────────────────
        on('toggle-edit-fields-btn', 'click', () => {
            const body    = document.getElementById('edit-fields-body');
            const chevron = document.getElementById('edit-fields-chevron');
            if (!body) return;
            const hidden = body.classList.toggle('hidden');
            chevron?.classList.toggle('rotate-180', !hidden);
            if (!hidden) {
                // Always load current ticket values so fields never appear empty
                const t = ui._ticketCache?.[ui.currentTicketId];
                if (t) {
                    document.getElementById('ef-descripcion').value  = t.descripcion || '';
                    document.getElementById('ef-numero_serie').value = t.numero_serie || '';
                    const prioSel = document.getElementById('ef-prioridad');
                    if (prioSel) prioSel.value = t.prioridad || 'Normal';
                    app._renderEfTags(t.tags || []);
                    // Store original values for dirty-checking
                    body.dataset.origDesc  = t.descripcion || '';
                    body.dataset.origSerie = t.numero_serie || '';
                    body.dataset.origPrio  = t.prioridad || 'Normal';
                    body.dataset.tagsDirty = 'false';  // reset dirty flag on open
                }
                ui.loadTagsIntoDetail();
            }
        });
        on('ef-add-tag', 'change', e => {
            if (!e.target.value) return;
            const nombre = e.target.value; e.target.value = '';
            const pills  = [...document.querySelectorAll('.ef-tag-pill')].map(p => ({ nombre: p.dataset.nombre, color: '#6366f1' }));
            if (pills.find(p => p.nombre === nombre)) return;
            app._renderEfTags([...pills, { nombre, color: '#6366f1' }]);
            // Mark tags as dirty so save knows to sync them
            const body = document.getElementById('edit-fields-body');
            if (body) body.dataset.tagsDirty = 'true';
        });
        on('save-edit-fields-btn', 'click', async () => {
            const id   = ui.currentTicketId;
            const body = document.getElementById('edit-fields-body');
            const desc = document.getElementById('ef-descripcion')?.value.trim();
            const serie = document.getElementById('ef-numero_serie')?.value.trim();
            const prio  = document.getElementById('ef-prioridad')?.value;
            const tagNombres = [...document.querySelectorAll('.ef-tag-pill')].map(p => p.dataset.nombre);

            // Only include fields that actually changed (fix: prevent clearing untouched fields)
            const changedFields = {};
            if (desc  !== (body?.dataset.origDesc  ?? '')) changedFields.descripcion   = desc;
            if (serie !== (body?.dataset.origSerie ?? '')) changedFields.numero_serie  = serie;
            if (prio  !== (body?.dataset.origPrio  ?? 'Normal')) changedFields.prioridad = prio;

            // Only sync tags if they were explicitly modified (dirty flag set by add/remove)
            const tagsDirty = body?.dataset.tagsDirty === 'true';

            try {
                if (Object.keys(changedFields).length > 0) {
                    await api.editTicketFields(id, changedFields);
                }
                if (tagsDirty) {
                    await api.setTags(id, tagNombres);
                }
                const refreshed = await api.getTicket(id);
                await ui.showTicketDetail(refreshed);
                document.getElementById('edit-fields-body')?.classList.add('hidden');
                document.getElementById('edit-fields-chevron')?.classList.remove('rotate-180');
                toast.success('Campos del ticket actualizados.');
            } catch(err) { toast.error(err.message); }
        });

        // ── Clone ticket ──────────────────────────────────────────────────
        on('clone-ticket-btn', 'click', async () => {
            const id = ui.currentTicketId;
            const ok = await confirmDialog('¿Clonar ticket?',
                'Se creará un nuevo ticket con los mismos datos, relacionado al original.', 'Clonar');
            if (!ok) return;
            try {
                const clone = await api.cloneTicket(id, true);
                toast.success(`Ticket clonado: ${clone.numero_rma}`);
                ui.showTicketDetail(clone);
            } catch(err) { toast.error(err.message); }
        });
        on('unlink-related-btn', 'click', async () => {
            const ok = await confirmDialog('¿Desasociar ticket relacionado?', 'El ticket dejará de estar vinculado.', 'Desasociar');
            if (!ok) return;
            try {
                await api.setTicketRelation(ui.currentTicketId, null);
                const unlinked = await api.getTicket(ui.currentTicketId);
                await ui.showTicketDetail(unlinked);
                toast.success('Ticket desasociado.');
            } catch(err) { toast.error(err.message); }
        });

        // ── Detail: parts list — edit/delete via event delegation ─────────────
        document.addEventListener('click', async e => {
            const ticketId = ui.currentTicketId;
            if (!ticketId) return;

            // Remove part
            const removeBtn = e.target.closest('.part-remove');
            if (removeBtn) {
                e.stopPropagation();
                const partId = parseInt(removeBtn.dataset.partId);
                const ok = await confirmDialog('¿Quitar repuesto?', 'El stock será devuelto automáticamente.', 'Quitar');
                if (!ok) return;
                try {
                    const cantidad = (JSON.parse(document.getElementById('detail-parts-list')?.dataset.parts || '[]')
                                      .find(p => p.id === partId) || {}).cantidad || 1;
                    const updated = await api.removeTicketPart(ticketId, partId);
                    await ui.showTicketDetail(updated);
                    toast.deshacer('Repuesto quitado del ticket (el stock volvió).', async () => {
                        const t = await api.addPart(ticketId, partId, cantidad);
                        if (ui.currentTicketId === ticketId) await ui.showTicketDetail(t);
                    });
                } catch(err) { toast.error(err.message); }
                return;
            }

            // Increment quantity
            const incBtn = e.target.closest('.part-qty-inc');
            if (incBtn) {
                e.stopPropagation();
                const partId = parseInt(incBtn.dataset.partId);
                const partsList = document.getElementById('detail-parts-list');
                const parts = JSON.parse(partsList?.dataset.parts || '[]');
                const part = parts.find(p => p.id === partId);
                if (!part) return;
                try {
                    const updated = await api.updateTicketPart(ticketId, partId, part.cantidad + 1);
                    await ui.showTicketDetail(updated);
                } catch(err) { toast.error(err.message); }
                return;
            }

            // Decrement quantity (min 1, or offer to remove)
            const decBtn = e.target.closest('.part-qty-dec');
            if (decBtn) {
                e.stopPropagation();
                const partId = parseInt(decBtn.dataset.partId);
                const partsList = document.getElementById('detail-parts-list');
                const parts = JSON.parse(partsList?.dataset.parts || '[]');
                const part = parts.find(p => p.id === partId);
                if (!part) return;
                if (part.cantidad <= 1) {
                    const ok = await confirmDialog('¿Quitar repuesto?', 'La cantidad es 1. Esto eliminará el repuesto del ticket y devolverá el stock.', 'Quitar');
                    if (!ok) return;
                    try {
                        const updated = await api.removeTicketPart(ticketId, partId);
                        await ui.showTicketDetail(updated);
                        toast.deshacer('Repuesto quitado del ticket (el stock volvió).', async () => {
                            const t = await api.addPart(ticketId, partId, 1);
                            if (ui.currentTicketId === ticketId) await ui.showTicketDetail(t);
                        });
                    } catch(err) { toast.error(err.message); }
                } else {
                    try {
                        const updated = await api.updateTicketPart(ticketId, partId, part.cantidad - 1);
                        await ui.showTicketDetail(updated);
                    } catch(err) { toast.error(err.message); }
                }
                return;
            }
        }, sig);

        // ── Diagnosis templates ──────────────────────────────────────────────
        document.querySelectorAll('.diag-template').forEach(btn => {
            btn.addEventListener('click', () => {
                const f = document.getElementById('update-diagnostic');
                if (!f) return;
                f.value = f.value.trim() ? f.value.trim() + '\n\n' + btn.dataset.text : btn.dataset.text;
                f.dispatchEvent(new Event('input', { bubbles: true }));   // habilita "Guardar diagnóstico"
                f.focus();
            }, sig);
        });

        // ── Inline description edit ──────────────────────────────────────────
        on('edit-description-btn', 'click', () => {
            const desc  = document.getElementById('detail-description');
            const form  = document.getElementById('edit-description-form');
            const input = document.getElementById('edit-description-input');
            if (!desc || !form || !input) return;
            input.value = desc.innerText;
            desc.classList.add('hidden');
            document.getElementById('edit-description-btn').classList.add('hidden');
            form.classList.remove('hidden');
            input.focus();
        });
        on('cancel-description-btn', 'click', () => {
            document.getElementById('edit-description-form')?.classList.add('hidden');
            document.getElementById('detail-description')?.classList.remove('hidden');
            document.getElementById('edit-description-btn')?.classList.remove('hidden');
        });
        on('save-description-btn', 'click', async () => {
            const val = document.getElementById('edit-description-input')?.value.trim();
            if (!val) { toast.warning('La descripción no puede estar vacía.'); return; }
            try {
                await api.editTicketFields(ui.currentTicketId, { descripcion: val });
                document.getElementById('detail-description').innerText = val;
                document.getElementById('edit-description-form').classList.add('hidden');
                document.getElementById('detail-description').classList.remove('hidden');
                document.getElementById('edit-description-btn').classList.remove('hidden');
                toast.success('Descripción actualizada.');
            } catch(e) { toast.error(e.message); }
        });

        // ── PDF print ─────────────────────────────────────────────────────
        on('print-pdf-btn',        'click', e => Documentos.menu(e.currentTarget));
        on('client-print-pdf-btn', 'click', e => Documentos.menu(e.currentTarget));

        // ── Detail: gestión del ticket ───────────────────────────────────
        // Cada control se guarda solo, en el momento: cambiar el estado no
        // arrastra el técnico, ni un repuesto elegido, ni el diagnóstico.
        Gestion.conectar(on);

        // ── Detail: adjuntos (frontend/js/adjuntos.js) ────────────────────
        Adjuntos.conectar(on);

        // La búsqueda global de la barra superior se conecta una sola vez
        // (frontend/js/busqueda.js): el campo no se recrea al navegar.
        Busqueda.iniciar();
        Barra.iniciar();
        Atajos.iniciar();

        // ── Search page ────────────────────────────────────────────────────
        on('back-to-dashboard-from-search', 'click', () => ui.initDashboard());

        on('search-page-input', 'keydown', e => {
            if (e.key === 'Enter') {
                const q = e.target.value.trim();
                if (q.length >= 2) ui.runSearch(q);
            }
        });

        onAll('.search-filter-btn', 'click', e => {
            const btn = e.currentTarget;
            {
                document.querySelectorAll('.search-filter-btn').forEach(b => {
                    b.classList.remove('bg-blue-600','text-white','border-blue-600');
                    b.classList.add('bg-white','text-gray-600');
                });
                btn.classList.add('bg-blue-600','text-white','border-blue-600');
                btn.classList.remove('bg-white','text-gray-600');
                ui._searchFilter = btn.dataset.value;
                ui.renderSearchResults();
            }
        });
    },

    // ── Public actions ─────────────────────────────────────────────────────

    async viewTicket(id) {
        try {
            const ticket = await api.getTicket(id);
            ui.showTicketDetail(ticket);
        } catch (err) { toast.error(err.message); }
    },

    async deleteUser(id) {
        const ok = await confirmDialog('¿Eliminar este usuario?', 'El usuario perderá acceso al sistema permanentemente.');
        if (!ok) return;
        try {
            await api.deleteUser(id);
            toast.success('Usuario eliminado.');
            if (document.getElementById('admin-section')) {
                const updated = await api.getUsers();
                ui._adminUsersCache = updated;
                document.getElementById('admin-user-count').textContent = updated.length;
                ui.adminRenderUsers();
            } else { ui.loadUsers(); }
        } catch (err) { toast.error(err.message); }
    },

    async deletePart(id) {
        const ok = await confirmDialog('¿Eliminar este repuesto?', 'Si está en uso en algún ticket no podrá eliminarse.');
        if (!ok) return;
        try {
            await api.deletePart(id);
            toast.success('Repuesto eliminado.');
            ui.loadPartsManagement();
        } catch (err) { toast.error(err.message); }
    },

    async deleteProduct(id) {
        const ok = await confirmDialog('¿Eliminar este producto?', 'No podrá eliminarse si tiene tickets asociados.');
        if (!ok) return;
        try {
            await api.deleteProduct(id);
            toast.success('Producto eliminado.');
            if (document.getElementById('admin-section')) {
                const updated = await api.getProducts();
                ui._adminProductsCache = updated;
                document.getElementById('admin-product-count').textContent = updated.length;
                ui.adminBuildProductCats();
                ui.adminRenderProducts();
            } else { ui.loadProducts(); }
        } catch (err) { toast.error(err.message); }
    },

    // ── Edit fields tag pills ─────────────────────────────────────────────────
    _renderEfTags(tags) {
        const cont = document.getElementById('ef-tags-container');
        if (!cont) return;
        cont.innerHTML = tags.map(t =>
            `<span class="ef-tag-pill flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold cursor-default"
                style="background:${colorSeguro(t.color, '#6366f1')}20;color:${colorSeguro(t.color, '#6366f1')};border:1px solid ${colorSeguro(t.color, '#6366f1')}50"
                data-nombre="${esc(t.nombre)}">
                ${esc(t.nombre)}
                <button type="button" class="ef-tag-remove font-bold leading-none hover:opacity-70" data-nombre="${esc(t.nombre)}">×</button>
            </span>`
        ).join('');
        cont.querySelectorAll('.ef-tag-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                const nombre    = btn.dataset.nombre;
                const remaining = [...document.querySelectorAll('.ef-tag-pill')]
                    .filter(p => p.dataset.nombre !== nombre)
                    .map(p => ({ nombre: p.dataset.nombre, color: p.style.color || '#6366f1' }));
                app._renderEfTags(remaining);
                // Mark tags as dirty
                const body = document.getElementById('edit-fields-body');
                if (body) body.dataset.tagsDirty = 'true';
            });
        });
    },


    // ── Reposición de Stock ───────────────────────────────────────────────────
    openReposicionModal() {
        const sel = document.getElementById('reposicion-part-id');
        if (!sel) return;
        sel.innerHTML = ui._adminPartsCache.map(p =>
            `<option value="${p.id}">${esc(p.nombre)} (stock: ${esc(p.stock)})</option>`
        ).join('');
        // Also populate the filter select
        const filterSel = document.getElementById('admin-stock-filter-part');
        if (filterSel && filterSel.options.length <= 1) {
            filterSel.innerHTML = '<option value="">Todos los repuestos</option>'
                + ui._adminPartsCache.map(p => `<option value="${p.id}">${esc(p.nombre)}</option>`).join('');
        }
        document.getElementById('reposicion-cantidad').value = '1';
        document.getElementById('reposicion-nota').value = '';
        document.getElementById('reposicion-modal').classList.remove('hidden');
    },

    async confirmarReposicion() {
        const partId   = parseInt(document.getElementById('reposicion-part-id')?.value);
        const cantidad = parseInt(document.getElementById('reposicion-cantidad')?.value);
        const nota     = document.getElementById('reposicion-nota')?.value || '';
        if (!partId || cantidad < 1) { toast.warning('Seleccioná un repuesto y una cantidad válida.'); return; }
        try {
            await api.reponerStock(partId, cantidad, nota);
            document.getElementById('reposicion-modal').classList.add('hidden');
            toast.success(`Stock actualizado: +${cantidad} unidades.`);
            // Refresh parts cache
            const updated = await api.getParts();
            ui._adminPartsCache = updated;
            document.getElementById('admin-parts-count').textContent = updated.length;
            ui.adminRenderParts();
            ui.adminCheckStockAlerts(updated);
            // Refresh stock history
            await ui.loadStockHistory();
        } catch(err) { toast.error(err.message); }
    },

    // ── Modal close confirm ───────────────────────────────────────────────────
    _modalDirty: false,
    trackModalDirty(formId) {
        const form = document.getElementById(formId);
        if (!form) return;
        form.querySelectorAll('input,textarea,select').forEach(el => {
            el.addEventListener('input',  () => { app._modalDirty = true; });
            el.addEventListener('change', () => { app._modalDirty = true; });
        });
    },
    async confirmModalClose(modalId) {
        if (!app._modalDirty) {
            document.getElementById(modalId)?.classList.add('hidden');
            return;
        }
        const ok = await confirmDialog('¿Descartar cambios?', 'Tenés cambios sin guardar. Si cerrás perderás la información ingresada.');
        if (ok) {
            document.getElementById(modalId)?.classList.add('hidden');
            app._modalDirty = false;
        }
    },
};

document.addEventListener('DOMContentLoaded', () => { ui.initDarkMode(); app.init(); });
