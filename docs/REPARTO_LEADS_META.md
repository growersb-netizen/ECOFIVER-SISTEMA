# Reparto de formularios Meta

El formulario **Plan 18 Pasos** de EcoFiver Módulos y Piscinas está vinculado a
**Viviendas modulares**. Cada formulario puede asociarse a viviendas o piscinas
desde **Aliados → Reparto de leads**, eligiendo página y formulario por nombre.

Cada vendedor tiene tres controles: participación general, viviendas y piscinas.
Sólo recibe consultas si está activo, tiene acceso y están encendidos tanto la
participación como el producto de la campaña. Las organizaciones tienen además
un control de participación por campaña. Los contratos de venta conservan sus
requisitos; no hace falta marcar contratos firmados para gestionar un lead.

El reparto es round robin: cada campaña mantiene un turno persistente entre sus
destinatarios habilitados. Desactivar a un vendedor lo excluye de próximos turnos
y conserva los leads y la gestión que ya tenía. Los asesores vinculados a una
cuenta de aliado participan una sola vez mediante esa cuenta.

Rodrigo puede administrar todo el reparto. Claudia Ríos (AL-010) puede administrar
a su organización y su propia participación desde **Panel de socios → Reparto
de leads**. Esta restricción tiene prioridad sobre su indicador administrativo
en otros módulos. Los cambios guardan autor, fecha y valores anteriores/nuevos.

Si una campaña está pausada o no tiene destinatarios disponibles, el formulario
se registra y queda pendiente. Al habilitar la campaña, la organización o un
vendedor se intentan asignar los pendientes mediante el mismo turno global.
Administración también dispone de **Repartir pendientes**. No se redistribuyen
leads con responsable ni se altera gestión existente.

El callback valida la firma de Meta y confirma la recepción después de persistir.
Consulta los datos con la identidad de la página resuelta desde el CRM y renueva
tokens de página vencidos usando la conexión global disponible. El evento Meta
tiene una recepción única; los reenvíos conservan datos, responsable y gestión.
Una falla del primer contacto de WhatsApp no elimina el registro en el CRM.

Para una campaña nueva: crear su formulario en Meta, elegirlo en el reparto,
seleccionar el producto, activar la campaña y habilitar los vendedores y
organizaciones correspondientes. El sistema comprueba la suscripción `leadgen`
al activar la campaña. Si Meta requiere reconectar la cuenta, la activación
informa el error en lugar de quedar funcionando sólo de forma aparente.

La migración 0038 agrega campañas, preferencias, participación por organización y
recepciones de Meta. Los controles nuevos comienzan apagados; la puesta en marcha
puede conservar explícitamente el grupo anterior desde la API o la interfaz.
Los reintentos externos siguen sujetos al servicio de Meta; no hay un proceso
programado de reconciliación con todos los formularios de la cuenta.
