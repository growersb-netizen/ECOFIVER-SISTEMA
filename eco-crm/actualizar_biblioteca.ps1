$BASE = "https://eco-crm-production.up.railway.app"
$HEADERS = @{ "Content-Type" = "application/json"; "X-API-Key" = "eco-crm-api-key-2024" }

$materiales = @(
  @{ id=229; titulo="Piscina rectangular - planta Zárate"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina rectangular verde turquesa terminada, vista interior en planta." }
  @{ id=230; titulo="Flyer - Socio Comercial (mujer)"; tipo="flyer"; categoria="redes"; descripcion="Flyer para redes sociales: Vendé Piscinas y Viviendas desde tu celular." }
  @{ id=231; titulo="Fabricación - laminado escalera piscina"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operarios laminando la escalera de una piscina en fábrica." }
  @{ id=232; titulo="Flyer - Ingresos Extra (hombre)"; tipo="flyer"; categoria="redes"; descripcion="Flyer para redes sociales: ¿Querés generar ingresos extra?" }
  @{ id=233; titulo="Fabricación - aplicación fibra de vidrio"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario aplicando fibra de vidrio a la pared grande de una piscina." }
  @{ id=234; titulo="Transporte - camión cargado con piscina"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Camión Scania blanco cargado con piscina verde en ruta." }
  @{ id=235; titulo="Entrega - descarga de piscina"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operarios descargando piscina del semirremolque en destino." }
  @{ id=236; titulo="Ficha Técnica - Módulo NCE 2x3m (negro)"; tipo="documento"; categoria="modulos"; descripcion="Ficha técnica del Módulo NCE 2×3m color negro, Modelo B." }
  @{ id=237; titulo="Flyer - Buscamos Vendedores"; tipo="flyer"; categoria="redes"; descripcion="Flyer de reclutamiento: Sumá tu Talento y Crecé con EcoFiver." }
  @{ id=238; titulo="Flyer - Revendedor de Piletas"; tipo="flyer"; categoria="redes"; descripcion="Flyer para revendedores de piletas interesados en sumar EcoFiver." }
  @{ id=239; titulo="Piscina rectangular color crema - planta"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina rectangular color crema/beige terminada, vista interior en planta." }
  @{ id=240; titulo="Flyer - Hidromasaje alta potencia"; tipo="flyer"; categoria="piscinas"; descripcion="Flyer del spa triangular de hidromasaje EcoFiver." }
  @{ id=241; titulo="Ficha Técnica - Módulo NCE 2x2m (blanco)"; tipo="documento"; categoria="modulos"; descripcion="Ficha técnica del Módulo A NCE 2×2m color blanco, Apto Comercial." }
  @{ id=242; titulo="Carga piscina en semirremolque - fábrica"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina oscura siendo cargada en semirremolque amarillo dentro de la fábrica." }
  @{ id=243; titulo="Flyer - Piscina Autoportante"; tipo="flyer"; categoria="piscinas"; descripcion="Flyer del modelo autoportante: piscina sin obra." }
  @{ id=244; titulo="Ficha Técnica - Módulo NCE 2x3m (blanco)"; tipo="documento"; categoria="modulos"; descripcion="Ficha técnica del Módulo B NCE 2×3m color blanco con ventanas." }
  @{ id=245; titulo="Transporte - semirremolque vacío"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Camión Scania blanco con semirremolque naranja vacío." }
  @{ id=246; titulo="Flyer - Financiá tu Piscina"; tipo="flyer"; categoria="piscinas"; descripcion="Flyer de financiación: Anticipate al verano, financiá tu piscina en cuotas." }
  @{ id=247; titulo="Fabricación - laminado exterior piscina"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario laminando el exterior de una piscina azul/verde grande." }
  @{ id=248; titulo="Flyer - Precio Promo Módulos"; tipo="flyer"; categoria="modulos"; descripcion="Flyer de promoción por tiempo limitado para módulos 6/12/18 m²." }
  @{ id=249; titulo="Flyer - Piscina Fibra Calidad"; tipo="flyer"; categoria="piscinas"; descripcion="Flyer de piscina de fibra: diseño, calidad y durabilidad." }
  @{ id=250; titulo="Flyer - Equipo Comercial (pareja)"; tipo="flyer"; categoria="redes"; descripcion="Flyer de equipo comercial: Convertí tu Experiencia en Resultados." }
  @{ id=251; titulo="Flyer - Revendedor de Piletas v2"; tipo="flyer"; categoria="redes"; descripcion="Flyer para revendedores con imagen de camión EcoFiver." }
  @{ id=252; titulo="Ficha Técnica - Módulo NCE 2x2m (negro)"; tipo="documento"; categoria="modulos"; descripcion="Ficha técnica del Módulo A NCE 2×2m color negro oscuro." }
  @{ id=253; titulo="Piscina rectangular con curvas - planta"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina rectangular verde con curvas decorativas, parada en planta." }
  @{ id=254; titulo="Entrega - Colón, Entre Ríos"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Collage de entrega: piscina azul instalada en Colón, Entre Ríos." }
  @{ id=255; titulo="Fabricación - laminado interior con máquina"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario laminando interior de piscina con máquina, vista cercana." }
  @{ id=256; titulo="Entrega - Módulo en Bella Vista"; tipo="foto_entrega"; categoria="modulos"; descripcion="Collage paso a paso de entrega e instalación de módulo en Bella Vista." }
  @{ id=257; titulo="Fabricación - carga piscina en planta"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operarios cargando piscina verde dentro de la planta de fabricación." }
  @{ id=258; titulo="Fabricación - pistola de fibra de vidrio"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario laminando piscina con pistola de fibra (proceso)." }
  @{ id=259; titulo="Fabricación - aplicación gelcoat"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario aplicando resina/gelcoat con pistola en piscina." }
  @{ id=260; titulo="Carga piscina con grúa - semirremolque"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina grande oscura siendo cargada con grúa en semirremolque." }
  @{ id=261; titulo="Entrega - descarga piscina grande"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operarios descargando piscina azul grande de semirremolque en instalación." }
  @{ id=262; titulo="Flyer - Equipo Comercial EcoFiver"; tipo="flyer"; categoria="redes"; descripcion="Flyer de reclutamiento: Sumate a nuestro Equipo Comercial." }
  @{ id=263; titulo="Fabricación - laminado exterior con manguera"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario laminando exterior de piscina azul con manguera de fibra de vidrio." }
  @{ id=264; titulo="Entrega - Punta Indio, Buenos Aires"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Collage de entrega: nueva pileta instalada en Punta Indio, Buenos Aires." }
  @{ id=265; titulo="Piscina azul con escalera - planta"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina azul grande parada en planta, vista interior con escalera." }
  @{ id=266; titulo="Flyer - Cabina de Seguridad"; tipo="flyer"; categoria="modulos"; descripcion="Flyer de la Cabina de Seguridad PRFV EcoFiver, 1.15x1.15x2.26m." }
  @{ id=267; titulo="Piscina terminada - interior verde y exterior negro"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Piscina terminada con interior verde turquesa y exterior negro reforzado." }
  @{ id=268; titulo="Fabricación - laminado escalera con spray"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operarios aplicando fibra con spray en la escalera interior de la piscina." }
  @{ id=269; titulo="Ficha Técnica - Módulo Vivienda 45m² (45B)"; tipo="documento"; categoria="modulos"; descripcion="Ficha técnica del Módulo 45B, 2 dormitorios, 45 m², sistema WoodFrame." }
  @{ id=270; titulo="Ficha Técnica - Módulo Vivienda 60m² (60B)"; tipo="documento"; categoria="modulos"; descripcion="Ficha técnica del Módulo 60B, 3 dormitorios, 60 m², sistema WoodFrame." }
  @{ id=271; titulo="Entrega - Módulo en Lima, Buenos Aires"; tipo="foto_entrega"; categoria="modulos"; descripcion="Collage de entrega de módulo NCE en Lima, Buenos Aires." }
  @{ id=272; titulo="Flyer - Vender Sin Stock (Socio Comercial)"; tipo="flyer"; categoria="redes"; descripcion="Flyer para socios: Empezá a Vender Sin Comprar Stock. EcoFiver fabrica, vos vendés." }
  @{ id=273; titulo="Fabricación - laminado pared con pistola"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Operario laminando pared grande de piscina con pistola de fibra de vidrio." }
  @{ id=274; titulo="Flyer - Vendé Financiación Viviendas"; tipo="flyer"; categoria="redes"; descripcion="Flyer de reclutamiento: Sumá tu Talento, Generá Ingresos, Vende Financiación de Viviendas." }
  @{ id=275; titulo="Entrega - Piscina instalada con camión"; tipo="foto_entrega"; categoria="piscinas"; descripcion="Collage de piscina azul instalada y camión con dos piscinas para entrega." }
)

$ok = 0; $err = 0
foreach ($m in $materiales) {
    $body = @{ titulo=$m.titulo; tipo=$m.tipo; categoria=$m.categoria; descripcion=$m.descripcion } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "$BASE/api/materiales-socio/$($m.id)" -Method PUT -Headers $HEADERS -Body $body
        Write-Host "OK $($m.id): $($m.titulo)"
        $ok++
    } catch {
        Write-Host "ERR $($m.id): $_"
        $err++
    }
    Start-Sleep -Milliseconds 200
}
Write-Host "`nResultado: $ok OK, $err errores"
