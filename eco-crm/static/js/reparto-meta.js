/* Controles de reparto compartidos por CRM y panel de socios. */
(() => {
  'use strict';
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const fields = {MODULO:'Viviendas', PISCINA:'Piscinas'};
  const path = value => encodeURIComponent(String(value));
  async function request(url, method = 'GET', body) {
    const response = await fetch(url, {method, credentials:'same-origin',
      headers:{'Content-Type':'application/json'}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo guardar el cambio. Intentá nuevamente.');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  class Reparto {
    constructor(container) {
      this.root = container;
      this.data = null;
      this.search = '';
      this.filter = '';
      this.busy = false;
      this.root.classList.add('rm');
      const heading = el('div','rm-heading');
      const title = el('div');
      title.append(el('h2',null,'Reparto de leads'), el('p','rm-muted','Elegí quién recibe consultas nuevas de viviendas y piscinas.'));
      this.refresh = el('button','rm-button','Actualizar');
      this.refresh.type = 'button';
      this.refresh.addEventListener('click',() => this.load().catch(() => {}));
      heading.append(title,this.refresh);
      this.status = el('p','rm-status');
      this.status.setAttribute('role','status');
      this.status.setAttribute('aria-live','polite');
      this.content = el('div');
      this.root.replaceChildren(heading,this.status,this.content);
    }
    setStatus(message, error = false) {
      this.status.textContent = message;
      this.status.classList.toggle('rm-error', error);
    }
    async load(options = {}) {
      this.refresh.disabled = true;
      this.root.setAttribute('aria-busy','true');
      this.setStatus('Cargando reparto…');
      try {
        this.data = await request('/api/reparto-meta');
        this.render();
        this.setStatus('Reparto actualizado.');
        return this.data;
      } catch (error) {
        if (options.silentDenied && [401,403].includes(error.status)) {
          this.content.replaceChildren();
          this.setStatus('');
          return null;
        }
        this.setStatus(error.message || 'No se pudo cargar el reparto.', true);
        throw error;
      } finally {
        this.refresh.disabled = false;
        this.root.setAttribute('aria-busy','false');
      }
    }
    async save(control, url, method, body) {
      if (this.busy) { if (control.type === 'checkbox') control.checked = !control.checked; return; }
      this.busy = true;
      let saved = false;
      const controls = [...this.root.querySelectorAll('input[type=checkbox],button')].map(node => [node,node.disabled]);
      controls.forEach(([node]) => { node.disabled = true; });
      const previous = control.type === 'checkbox' ? !control.checked : null;
      const group = control.closest('fieldset') || control;
      group.disabled = true;
      this.setStatus('Guardando…');
      try {
        await request(url,method,body);
        saved = true;
        await this.load();
        this.setStatus('Cambios guardados. Se aplican a las próximas consultas.');
      } catch (error) {
        if (!saved && previous !== null) control.checked = previous;
        this.setStatus(saved ? 'El cambio se guardó, pero no se pudo actualizar la vista. Tocá Actualizar.' : error.message, true);
      } finally {
        group.disabled = false;
        controls.forEach(([node,disabled]) => { if (node.isConnected) node.disabled = disabled; });
        this.busy = false;
      }
    }
    switch(label, checked, onChange, disabled = false) {
      const wrap = el('label','rm-switch');
      const input = el('input');
      input.type = 'checkbox';
      input.checked = Boolean(checked);
      input.disabled = disabled;
      input.setAttribute('role','switch');
      input.setAttribute('aria-label',label);
      const track = el('span','rm-track');
      track.setAttribute('aria-hidden','true');
      wrap.append(input,track,el('span','rm-switch-label',label));
      input.addEventListener('change',() => onChange(input));
      return wrap;
    }
    render() {
      const data = this.data;
      const global = data.alcance === 'global';
      const contents = document.createDocumentFragment();
      this.summary = el('div','rm-summary');
      const destinations = data.destinatarios || [];
      const enabled = destinations.filter(d => d.habilitado && d.elegible !== false);
      const count = el('div','rm-count');
      count.append(el('strong',null,String(enabled.length)),el('span',null,'vendedores habilitados'));
      this.summary.append(count);
      const pending = Number(typeof data.pendientes === 'number' ? data.pendientes : data.pendientes?.total || 0);
      const pendingCount = el('div','rm-count');
      pendingCount.append(el('strong',null,String(pending)),el('span',null,'consultas pendientes de asignación'));
      this.summary.append(pendingCount);
      if (!enabled.length) this.summary.append(el('p','rm-warning','No hay vendedores habilitados en este alcance. Las consultas quedarán pendientes hasta que haya un destinatario disponible.'));
      if (data.puede_repartir_pendientes) {
        const distribute = el('button','rm-button','Repartir pendientes');
        distribute.type = 'button';
        distribute.disabled = !pending;
        distribute.addEventListener('click',() => this.save(distribute,'/api/reparto-meta/pendientes','POST',{}));
        this.summary.append(distribute);
      }
      contents.append(this.summary);
      if (!global) contents.append(el('p','rm-scope','Administrás únicamente el reparto de tu organización.'));
      contents.append(this.campaigns(global));
      const team = el('section','rm-card');
      team.append(el('h3',null,'Vendedores que reciben consultas'));
      team.append(el('p','rm-muted','La participación y los productos se guardan por vendedor. Los leads que ya tiene asignados conservan su responsable.'));
      const filters = el('div','rm-filters');
      const searchLabel = el('label');
      searchLabel.append(el('span','rm-field-label','Buscar vendedor'));
      const search = el('input','rm-input');
      search.type = 'search';
      search.placeholder = 'Nombre, código u organización';
      search.value = this.search;
      search.addEventListener('input',() => { this.search = search.value; this.renderDestinations(); });
      searchLabel.append(search);
      const filterLabel = el('label');
      filterLabel.append(el('span','rm-field-label','Mostrar'));
      const filter = el('select','rm-input');
      [['','Todos'],['habilitados','Participan'],['pausados','Pausados'],['MODULO','Viviendas'],['PISCINA','Piscinas'],['aliado','Aliados'],['asesor','Asesores']].forEach(([value,label]) => {
        const option = el('option',null,label); option.value = value; filter.append(option);
      });
      filter.value = this.filter;
      filter.addEventListener('change',() => { this.filter = filter.value; this.renderDestinations(); });
      filterLabel.append(filter);
      this.resultCount = el('p','rm-muted');
      this.resultCount.setAttribute('aria-live','polite');
      filters.append(searchLabel,filterLabel);
      this.list = el('div','rm-destinations');
      team.append(filters,this.resultCount,this.list);
      contents.append(team);
      if (global && data.puede_crear_campanas !== false) contents.append(this.campaignForm());
      this.content.replaceChildren(contents);
      this.renderDestinations();
    }
    renderDestinations() {
      const query = this.search.trim().toLocaleLowerCase('es');
      const all = this.data.destinatarios || [];
      const visible = all.filter(d => {
        const matches = [d.nombre,d.codigo,d.organizacion_codigo,d.organizacion_nombre].join(' ').toLocaleLowerCase('es').includes(query);
        const kind = String(d.tipo || '').toLowerCase();
        const filter = this.filter;
        return matches && (!filter || filter === 'habilitados' && d.habilitado || filter === 'pausados' && !d.habilitado || filter === 'MODULO' && d.modulos || filter === 'PISCINA' && d.piscinas || filter === kind);
      });
      this.resultCount.textContent = `${visible.length} de ${all.length} vendedores`;
      this.list.replaceChildren();
      if (!visible.length) this.list.append(el('p','rm-empty',query || this.filter ? 'No hay vendedores para esta búsqueda.' : 'No hay vendedores disponibles en este alcance.'));
      visible.forEach(d => {
        const row = el('fieldset','rm-destination');
        const legend = el('legend','rm-visually-hidden',d.nombre || d.codigo || d.clave);
        const identity = el('div','rm-identity');
        identity.append(el('strong',null,d.nombre || 'Sin nombre'));
        identity.append(el('span','rm-muted',[d.codigo || d.clave,d.tipo === 'asesor' ? 'Asesor' : 'Aliado',d.organizacion_nombre || d.organizacion_codigo].filter(Boolean).join(' · ')));
        if (d.elegible === false) identity.append(el('span','rm-warning',d.motivo || 'No cumple los requisitos para recibir consultas.'));
        const switches = el('div','rm-destination-switches');
        [['habilitado','Participa'],['modulos','Viviendas'],['piscinas','Piscinas']].forEach(([key,label]) => {
          const toggle = this.switch(`${label}: ${d.nombre || d.codigo}`,d[key],control => this.save(control,`/api/reparto-meta/destinos/${path(d.clave)}`,'PATCH',{[key]:control.checked}));
          toggle.lastChild.textContent = label;
          switches.append(toggle);
        });
        row.append(legend,identity,switches);
        this.list.append(row);
      });
    }
    campaigns(global) {
      const section = el('section','rm-card');
      section.append(el('h3',null,'Campañas y formularios'));
      section.append(el('p','rm-muted',global ? 'Cada formulario se vincula a un producto. Activá una campaña para recibir sus próximas consultas.' : 'Activá las campañas en las que participa tu organización.'));
      const campaigns = this.data.campanas || [];
      if (!campaigns.length) section.append(el('p','rm-empty','Todavía no hay formularios vinculados.'));
      campaigns.forEach(c => {
        const row = el('fieldset','rm-campaign');
        row.append(el('legend','rm-visually-hidden',c.nombre));
        const info = el('div','rm-identity');
        info.append(el('strong',null,c.nombre || c.form_id));
        info.append(el('span','rm-muted',`${fields[c.producto] || 'Producto sin definir'} · ${c.activa ? 'Campaña activa' : 'Campaña pausada'}`));
        row.append(info);
        if (global) {
          row.append(this.switch(`Campaña activa: ${c.nombre}`,c.activa,control => this.save(control,`/api/reparto-meta/campanas/${path(c.form_id)}`,'PUT',{form_id:c.form_id,page_id:c.page_id,nombre:c.nombre,producto:c.producto,activa:control.checked})));
        } else {
          const codigo = this.data.organizacion_codigo;
          row.append(this.switch(`Mi organización participa en ${c.nombre}`,c.habilitada_organizacion,control => this.save(control,`/api/reparto-meta/organizaciones/${path(codigo)}/campanas/${path(c.form_id)}`,'PATCH',{habilitada:control.checked}),!c.activa));
        }
        section.append(row);
      });
      if (global && this.data.organizaciones?.length && campaigns.length) {
        const details = el('details','rm-orgs');
        details.append(el('summary',null,'Participación por organización'));
        this.data.organizaciones.forEach(org => {
          const group = el('fieldset','rm-org');
          group.append(el('legend',null,org.nombre || org.codigo));
          campaigns.forEach(c => group.append(this.switch(`${c.nombre} · ${org.nombre || org.codigo}`,Boolean(org.campanas?.[c.form_id]),control => this.save(control,`/api/reparto-meta/organizaciones/${path(org.codigo)}/campanas/${path(c.form_id)}`,'PATCH',{habilitada:control.checked}))));
          details.append(group);
        });
        section.append(details);
      }
      return section;
    }
    campaignForm() {
      const details = el('details','rm-card');
      details.append(el('summary',null,'Agregar o actualizar una campaña'));
      const form = el('form','rm-campaign-form');
      form.append(el('p','rm-muted','Elegí la página y el formulario de Facebook. El sistema reconoce si ya está vinculado para actualizarlo sin duplicar la campaña.'));
      const labeled = (label, input) => {
        const wrap = el('label'); wrap.append(el('span','rm-field-label',label),input); form.append(wrap);
      };
      const option = (select, value, text) => { const node = el('option',null,text); node.value = value; select.append(node); return node; };
      const page = el('select','rm-input'); page.name = 'page_id'; page.required = true;
      option(page,'','Elegí una página');
      (this.data.paginas || []).forEach(p => option(page,p.page_id,p.nombre || 'Página de Facebook'));
      labeled('Página de Facebook',page);
      const metaForm = el('select','rm-input'); metaForm.name = 'form_id'; metaForm.required = true; metaForm.disabled = true;
      option(metaForm,'','Primero elegí una página');
      labeled('Formulario de clientes potenciales',metaForm);
      const formStatus = el('p','rm-muted rm-full'); formStatus.setAttribute('role','status'); formStatus.setAttribute('aria-live','polite');
      const retry = el('button','rm-button rm-retry','Reintentar carga de formularios'); retry.type = 'button'; retry.hidden = true;
      form.append(formStatus,retry);
      const name = el('input','rm-input'); name.name = 'nombre'; name.required = true; name.maxLength = 150; name.placeholder = 'Se completa al elegir el formulario';
      labeled('Nombre de la campaña',name);
      const product = el('select','rm-input'); product.name = 'producto'; product.required = true;
      option(product,'','Elegí un producto');
      Object.entries(fields).forEach(([value,text]) => option(product,value,text));
      labeled('Producto',product);
      const active = this.switch('Campaña activa',true,()=>{}); active.classList.add('rm-full');
      const activeInput = active.querySelector('input');
      form.append(active);
      const submit = el('button','rm-button','Guardar campaña'); submit.type = 'submit'; submit.disabled = true; form.append(submit);
      let forms = [];
      let loadVersion = 0;
      function chosen() {
        return forms.find(item => String(item.id) === metaForm.value);
      }
      const chooseForm = () => {
        const selected = chosen();
        const existing = (this.data.campanas || []).find(c => String(c.form_id) === metaForm.value);
        name.value = existing?.nombre || selected?.name || '';
        product.value = existing?.producto || '';
        activeInput.checked = existing ? Boolean(existing.activa) : true;
        submit.disabled = !selected;
        submit.textContent = existing ? 'Actualizar campaña' : 'Vincular campaña';
        formStatus.textContent = existing ? 'Este formulario ya tiene una campaña. Guardar actualizará su nombre, producto y participación.' : '';
      };
      const loadForms = async () => {
        const version = ++loadVersion;
        forms = [];
        metaForm.replaceChildren();
        name.value = '';
        product.value = '';
        submit.disabled = true;
        retry.hidden = true;
        if (!page.value) {
          option(metaForm,'','Primero elegí una página'); metaForm.disabled = true; formStatus.textContent = ''; return;
        }
        option(metaForm,'','Cargando formularios…'); metaForm.disabled = true; retry.disabled = true;
        formStatus.textContent = 'Consultando los formularios de esta página…';
        formStatus.classList.remove('rm-error');
        try {
          const result = await request('/api/reparto-meta/formularios?page_id=' + path(page.value));
          if (version !== loadVersion) return;
          forms = result.forms || [];
          metaForm.replaceChildren();
          option(metaForm,'',forms.length ? 'Elegí un formulario' : 'No hay formularios disponibles');
          forms.forEach(item => {
            const archived = String(item.status || '').toUpperCase() === 'ARCHIVED';
            const entry = option(metaForm,String(item.id),(item.name || 'Formulario sin nombre') + (archived ? ' · Archivado' : ''));
            entry.disabled = archived;
          });
          metaForm.disabled = !forms.length;
          formStatus.textContent = forms.length ? 'Formularios cargados. Elegí el que usará la campaña.' : 'Esta página no tiene formularios disponibles. Podés crearlos en Facebook y volver a consultar.';
          if (result.has_more) formStatus.textContent += ' La lista es parcial; hay más formularios en esta página.';
          retry.hidden = false;
        } catch (error) {
          if (version !== loadVersion) return;
          metaForm.replaceChildren(); option(metaForm,'','No se pudieron cargar los formularios'); metaForm.disabled = true;
          formStatus.textContent = error.message || 'No se pudieron consultar los formularios. Revisá el acceso a esta página desde Redes y reintentá.';
          formStatus.classList.add('rm-error'); retry.hidden = false;
        } finally {
          if (version === loadVersion) retry.disabled = false;
        }
      };
      page.addEventListener('change',loadForms);
      retry.addEventListener('click',loadForms);
      metaForm.addEventListener('change',chooseForm);
      form.addEventListener('submit',event => {
        event.preventDefault();
        if (!chosen() || !product.value || !name.value.trim()) return;
        const values = {nombre:name.value.trim(),page_id:page.value,form_id:metaForm.value,producto:product.value,activa:activeInput.checked};
        const existing = (this.data.campanas || []).some(c => String(c.form_id) === values.form_id);
        this.save(submit,existing ? '/api/reparto-meta/campanas/' + path(values.form_id) : '/api/reparto-meta/campanas',existing ? 'PUT' : 'POST',values);
      });
      if (!(this.data.paginas || []).length) formStatus.textContent = 'No hay páginas conectadas. Conectá la página de Facebook desde Redes para elegir sus formularios.';
      details.append(form);
      return details;
    }
  }
  window.RepartoMetaUI = {mount: container => new Reparto(container)};
})();
