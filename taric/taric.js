const { chromium } = require('playwright');
const path = require('path');
const os = require('os');
const fs = require('fs');
const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);

(async () => {
  // Crear un directorio temporal para el perfil de Playwright
  // Esto evita conflictos si Chrome está abierto
  const tempProfileDir = path.join(os.tmpdir(), 'playwright-chrome-profile-' + Date.now());
  
  // Intentar copiar certificados del perfil de Chrome si existe
  const chromeUserData = path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data');
  const chromeDefaultProfile = path.join(chromeUserData, 'Default');
  
  console.log('📁 Creando perfil temporal:', tempProfileDir);
  
  // Crear el directorio temporal
  if (!fs.existsSync(tempProfileDir)) {
    fs.mkdirSync(tempProfileDir, { recursive: true });
  }

  // Intentar copiar los certificados si Chrome no está en uso
  try {
    if (fs.existsSync(chromeDefaultProfile)) {
      const certPath = path.join(chromeDefaultProfile, 'Default', 'Web Data');
      const tempCertPath = path.join(tempProfileDir, 'Web Data');
      if (fs.existsSync(certPath)) {
        console.log('📋 Intentando copiar certificados...');
        // Nota: En Windows, los certificados están en el almacén del sistema, no en archivos
        // Pero copiamos la configuración del perfil por si acaso
      }
    }
  } catch (error) {
    console.log('⚠️  No se pudieron copiar certificados (Chrome puede estar abierto):', error.message);
    console.log('💡 Cierra Chrome antes de ejecutar el script, o selecciona el certificado manualmente');
  }

  console.log('🚀 Iniciando navegador con perfil temporal...');

  const browser = await chromium.launchPersistentContext(tempProfileDir, {
    headless: false,
    args: [
      '--ignore-certificate-errors',
      '--allow-running-insecure-content',
      '--auto-open-devtools-for-tabs',
      // Argumentos para mejorar el manejo de certificados
      '--enable-features=NetworkService,NetworkServiceInProcess',
      '--disable-web-security', // Solo para desarrollo, permite certificados
      // Usar el almacén de certificados de Windows
      '--use-system-default-printer',
      '--enable-native-gpu-memory-buffers',
    ],
    // Configurar el contexto para aceptar certificados
    acceptDownloads: true,
    ignoreHTTPSErrors: true,
  });

  const page = await browser.newPage();

  // Variable global para rastrear si ya se presionó Enter
  let enterPressed = false;

  // Función para hacer clic automáticamente en el diálogo de certificado de Windows
  const clickCertificateDialog = async () => {
    // Si ya se presionó Enter, no intentar de nuevo
    if (enterPressed) {
      return false;
    }
    
    try {
      // Script PowerShell mejorado que busca el diálogo de certificado y selecciona el primero
      const psScript = `
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32 {
  [DllImport("user32.dll")]
  public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
  [DllImport("user32.dll")]
  public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
  [DllImport("user32.dll")]
  public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")]
  public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")]
  public static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  
  public const uint WM_KEYDOWN = 0x0100;
  public const uint WM_KEYUP = 0x0101;
  public const uint WM_LBUTTONDOWN = 0x0201;
  public const uint WM_LBUTTONUP = 0x0202;
  public const uint VK_RETURN = 0x0D;
  public const uint VK_TAB = 0x09;
  public const uint VK_DOWN = 0x28;
}

public class DialogInfo {
  public IntPtr hwnd;
  public string title;
}
"@

$found = $false
$attempts = 0
$maxAttempts = 40

while (-not $found -and $attempts -lt $maxAttempts) {
  # Buscar diálogo modal (#32770 es la clase estándar de diálogos modales)
  $dialogHwnd = [Win32]::FindWindow("#32770", $null)
  
  if ($dialogHwnd -ne [IntPtr]::Zero -and [Win32]::IsWindowVisible($dialogHwnd)) {
    $title = New-Object System.Text.StringBuilder 256
    [Win32]::GetWindowText($dialogHwnd, $title, 256) | Out-Null
    $titleText = $title.ToString().ToLower()
    
    # Verificar si es un diálogo de certificado
    if ($titleText -like "*certificado*" -or $titleText -like "*certificate*" -or 
        $titleText -like "*seleccionar*" -or $titleText -like "*select*" -or
        $titleText -eq "" -or $titleText -like "*chrome*") {
      
      Write-Host "Diálogo encontrado: $titleText"
      
      # Activar la ventana
      [Win32]::SetForegroundWindow($dialogHwnd) | Out-Null
      Start-Sleep -Milliseconds 500
      
      # El primer certificado suele estar seleccionado por defecto
      # Presionar Tab para asegurarse de que estamos en el área correcta
      [Win32]::SendMessage($dialogHwnd, [Win32]::WM_KEYDOWN, [IntPtr]0x09, [IntPtr]::Zero) | Out-Null
      Start-Sleep -Milliseconds 100
      [Win32]::SendMessage($dialogHwnd, [Win32]::WM_KEYUP, [IntPtr]0x09, [IntPtr]::Zero) | Out-Null
      Start-Sleep -Milliseconds 200
      
      # Presionar Enter para aceptar (el primer certificado ya está seleccionado)
      [Win32]::SendMessage($dialogHwnd, [Win32]::WM_KEYDOWN, [IntPtr]0x0D, [IntPtr]::Zero) | Out-Null
      Start-Sleep -Milliseconds 100
      [Win32]::SendMessage($dialogHwnd, [Win32]::WM_KEYUP, [IntPtr]0x0D, [IntPtr]::Zero) | Out-Null
      
      Write-Output "OK"
      $found = $true
      break
    }
  }
  
  # También buscar ventanas de Chrome/Chromium que puedan tener el diálogo
  $chromeProcs = Get-Process | Where-Object { 
    ($_.ProcessName -like "*chrome*" -or $_.ProcessName -like "*chromium*") -and
    $_.MainWindowTitle -ne ""
  }
  
  foreach ($proc in $chromeProcs) {
    try {
      # Intentar activar y presionar Enter (método simple)
      Add-Type -AssemblyName Microsoft.VisualBasic
      [Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null
      Start-Sleep -Milliseconds 300
      
      # Enviar Enter directamente
      Add-Type -AssemblyName System.Windows.Forms
      [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
      Start-Sleep -Milliseconds 200
      
      # Si hay un diálogo, esto debería seleccionarlo
    } catch {
      # Continuar
    }
  }
  
  if (-not $found) {
    Start-Sleep -Milliseconds 500
    $attempts++
  }
}

if (-not $found) {
  Write-Output "NOTFOUND"
}
      `;
      
      // Guardar script PowerShell en archivo temporal
      const psPath = path.join(os.tmpdir(), `cert-dialog-${Date.now()}.ps1`);
      fs.writeFileSync(psPath, psScript);
      
      try {
        const psResult = await execAsync(`powershell -ExecutionPolicy Bypass -File "${psPath}"`, {
          timeout: 20000,
          shell: true
        });
        
        try {
          fs.unlinkSync(psPath);
        } catch (e) {}
        
        if (psResult.stdout && psResult.stdout.includes('OK')) {
          console.log('✅ Certificado seleccionado automáticamente');
          enterPressed = true; // Marcar que ya se presionó Enter
          return true;
        }
      } catch (psError) {
        try {
          fs.unlinkSync(psPath);
        } catch (e) {}
      }
      
      // NO ejecutar el método alternativo simple aquí - solo si el principal falla completamente
      // Esto evita presionar Enter múltiples veces
      
    } catch (error) {
      // Silenciar errores
    }
    return false;
  };

  // Iniciar la detección del diálogo en segundo plano (cada 200ms para ser más agresivo)
  let dialogWatcher;
  let dialogFound = false;
  let attemptCount = 0;

  console.log('🌐 Navegando a la URL de la Agencia Tributaria...');
  console.log('🔐 El script intentará seleccionar automáticamente el primer certificado del diálogo.');
  
  // Iniciar el watcher del diálogo ANTES de navegar
  dialogWatcher = setInterval(async () => {
    if (!dialogFound && !enterPressed) {
      attemptCount++;
      if (attemptCount % 10 === 0) {
        console.log(`   🔍 Intentando detectar diálogo... (intento ${attemptCount})`);
      }
      const result = await clickCertificateDialog();
      if (result || enterPressed) {
        dialogFound = true;
        enterPressed = true;
        clearInterval(dialogWatcher);
        dialogWatcher = null; // Limpiar la referencia
        console.log('✅ Diálogo de certificado manejado, esperando navegación...');
      }
    } else if (dialogFound || enterPressed) {
      // Si ya se encontró, detener el watcher
      clearInterval(dialogWatcher);
      dialogWatcher = null;
    }
  }, 200);
  
  // Iniciar navegación de forma asíncrona (no esperar todavía)
  console.log('⏳ Iniciando navegación...');
  const navigationPromise = page.goto('https://www1.agenciatributaria.gob.es/wlpl/inwinvoc/es.aeat.dit.adu.adta.trans.bdm.TtCodNomIntQuery', {
    waitUntil: 'domcontentloaded',
    timeout: 120000  // Aumentar timeout porque el diálogo puede tardar
  }).catch(err => {
    // El error es esperado si el diálogo bloquea la navegación
    if (err.message.includes('Timeout')) {
      console.log('⏳ Navegación en espera (diálogo de certificado detectado)...');
    }
  });

  // Esperar un momento para que aparezca el diálogo
  console.log('🔍 Esperando a que aparezca el diálogo de certificado...');
  await page.waitForTimeout(2000);
  
  // Intentar seleccionar el certificado de forma agresiva
  console.log('🔄 Intentando seleccionar certificado de forma agresiva...');
  for (let i = 0; i < 30; i++) {
    if (dialogFound || enterPressed) {
      break;
    }
    if (await clickCertificateDialog()) {
      dialogFound = true;
      enterPressed = true;
      console.log(`✅ Certificado seleccionado en intento ${i + 1}`);
      break;
    }
    await page.waitForTimeout(300);
    if (i % 10 === 0 && i > 0) {
      console.log(`   🔄 Continuando búsqueda... (intento ${i + 1}/30)`);
    }
  }
  
  // Detener el watcher si aún está activo
  if (dialogWatcher) {
    clearInterval(dialogWatcher);
    dialogWatcher = null;
    enterPressed = true; // Asegurar que no se intente más
  }
  
  // Esperar un momento adicional después de seleccionar el certificado
  if (dialogFound) {
    console.log('⏳ Esperando a que se procese la selección del certificado...');
    await page.waitForTimeout(2000);
  }
  
  // Ahora esperar a que termine la navegación
  console.log('⏳ Esperando a que complete la navegación...');
  try {
    await navigationPromise;
    console.log('✅ Navegación completada');
  } catch (err) {
    // Si aún hay timeout, intentar recargar
    if (err.message.includes('Timeout')) {
      console.log('⚠️  Timeout en navegación, intentando recargar...');
      try {
        await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
        console.log('✅ Página recargada');
      } catch (reloadErr) {
        console.log('⚠️  Error al recargar:', reloadErr.message);
      }
    }
  }

  // Esperar un momento adicional para que se procese la autenticación con certificado
  await page.waitForTimeout(2000);

  // Verificar si hay un diálogo de selección de certificado
  // Si la página muestra un error 403, significa que no se seleccionó el certificado
  const pageContent = await page.content();
  
  if (pageContent.includes('403') || pageContent.includes('Error de identificación')) {
    console.log('⚠️  Error 403 detectado. El certificado no se seleccionó automáticamente.');
    console.log('💡 Asegúrate de que:');
    console.log('   1. El certificado está instalado en Chrome');
    console.log('   2. El certificado está configurado como predeterminado');
    console.log('   3. Estás usando el perfil correcto de Chrome');
    
    // Esperar 10 segundos para que el usuario pueda seleccionar el certificado manualmente si aparece el diálogo
    console.log('⏳ Esperando 10 segundos por si aparece el diálogo de selección de certificado...');
    await page.waitForTimeout(10000);
  } else {
    console.log('✅ Página cargada correctamente. El certificado parece haberse seleccionado automáticamente.');
  }

  // Extraer HTML
  const html = await page.content();
  console.log('\n=== HTML de la página ===');
  console.log(html.substring(0, 1000)); // Mostrar solo los primeros 1000 caracteres
  console.log('...\n');

  // Guardar el HTML en un archivo para inspección
  const outputPath = path.join(__dirname, 'output.html');
  fs.writeFileSync(outputPath, html);
  console.log(`📄 HTML guardado en: ${outputPath}`);

  // No cerrar el navegador automáticamente para poder inspeccionar
  console.log('\n⚠️  El navegador permanecerá abierto. Presiona Ctrl+C para cerrar.');
  console.log('💡 Si aparece un diálogo de selección de certificado, selecciónalo manualmente.');
  
  // Mantener el proceso activo
  const cleanup = async () => {
    console.log('\n🧹 Cerrando navegador y limpiando...');
    try {
      // Detener el watcher si aún está activo
      if (dialogWatcher) {
        clearInterval(dialogWatcher);
      }
      await browser.close();
      // Limpiar el perfil temporal
      if (fs.existsSync(tempProfileDir)) {
        fs.rmSync(tempProfileDir, { recursive: true, force: true });
        console.log('✅ Perfil temporal eliminado');
      }
    } catch (error) {
      console.log('⚠️  Error al limpiar:', error.message);
    }
    process.exit(0);
  };

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
})();
