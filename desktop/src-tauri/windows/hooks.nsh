; OpenConstructionERP - NSIS installer hooks
;
; Windows keeps an exclusive lock on a running .exe. If the backend sidecar
; (openconstructionerp-server.exe) is still running when the installer tries to
; overwrite it, or when the uninstaller tries to delete it, the operation fails
; with "file in use by another process". That is the reinstall error users hit:
; after the app is closed or uninstalled the sidecar can linger in the
; background, and the next install cannot replace the locked file until the
; process is stopped by hand in Task Manager.
;
; These hooks stop the app and its backend sidecar automatically, before the
; installer writes files and before the uninstaller removes them, so the file
; lock is gone by the time it matters. Both the current name and the former
; "openestimate-server" name are stopped, so upgrading from an older install is
; never blocked by a still-running old process either.
;
; taskkill is a standard Windows tool. /F forces termination, /T also stops the
; child processes the sidecar started (the embedded PostgreSQL server). A
; missing process just makes taskkill return non-zero, which nsExec swallows, so
; running these when nothing is up is harmless. The short Sleep gives Windows a
; moment to release the file handle after the process exits.

!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Stopping any running OpenConstructionERP processes..."
  nsExec::Exec 'taskkill /F /T /IM openconstructionerp-server.exe'
  nsExec::Exec 'taskkill /F /T /IM openestimate-server.exe'
  nsExec::Exec 'taskkill /F /T /IM OpenConstructionERP.exe'
  Sleep 800
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Stopping any running OpenConstructionERP processes..."
  nsExec::Exec 'taskkill /F /T /IM openconstructionerp-server.exe'
  nsExec::Exec 'taskkill /F /T /IM openestimate-server.exe'
  nsExec::Exec 'taskkill /F /T /IM OpenConstructionERP.exe'
  Sleep 800
!macroend
