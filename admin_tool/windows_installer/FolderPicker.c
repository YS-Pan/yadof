/* Immediate MSI UI action: the Windows Common Item Dialog in folder mode. */
#define COBJMACROS
#include <windows.h>
#include <msi.h>
#include <msiquery.h>
#include <shobjidl.h>
#include <wchar.h>

typedef struct {
    WCHAR initial[32768];
    PWSTR selected;
    HRESULT result;
} Picker;

static BOOL path_fits(MSIHANDLE session, LPCWSTR path)
{
    WCHAR value[32];
    DWORD capacity = ARRAYSIZE(value);
    if (MsiGetPropertyW(session, L"MAXINSTALLDIRCHARS", value, &capacity) != ERROR_SUCCESS) return FALSE;
    unsigned long maximum = wcstoul(value, NULL, 10);
    size_t length = wcslen(path);
    while (length > 3 && (path[length - 1] == L'\\' || path[length - 1] == L'/')) --length;
    return maximum > 0 && length <= maximum;
}

static const WCHAR path_error[] = L"The installation folder path is too long. "
    L"Choose a shorter path, for example C:\\Apps\\Yadof.";

__declspec(dllexport) UINT __stdcall CheckInstallFolder(MSIHANDLE session)
{
    WCHAR path[32768];
    DWORD capacity = ARRAYSIZE(path);
    UINT status = MsiGetPropertyW(session, L"INSTALLDIR", path, &capacity);
    if (status != ERROR_SUCCESS) return status;
    BOOL valid = path_fits(session, path);
    MsiSetPropertyW(session, L"YADOFINSTALLDIROK", valid ? L"1" : L"0");
    if (!valid) MessageBoxW(NULL, path_error, L"Choose a shorter installation folder", MB_OK | MB_ICONWARNING);
    return ERROR_SUCCESS;
}

__declspec(dllexport) UINT __stdcall CheckInstallFolderForExecute(MSIHANDLE session)
{
    WCHAR path[32768];
    DWORD capacity = ARRAYSIZE(path);
    UINT status = MsiGetPropertyW(session, L"INSTALLDIR", path, &capacity);
    if (status != ERROR_SUCCESS) return status;
    if (path_fits(session, path)) return ERROR_SUCCESS;
    MSIHANDLE message = MsiCreateRecord(0);
    MsiRecordSetStringW(message, 0, path_error);
    MsiProcessMessage(session, INSTALLMESSAGE_ERROR, message);
    MsiCloseHandle(message);
    return ERROR_INSTALL_FAILURE;
}

static void choose_folder(Picker *picker)
{
    IFileOpenDialog *dialog = NULL;
    IShellItem *folder = NULL;
    IShellItem *selected = NULL;
    FILEOPENDIALOGOPTIONS options;
    HRESULT initialized = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    picker->result = initialized;
    if (FAILED(initialized)) return;

    picker->result = CoCreateInstance(&CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER,
                                      &IID_IFileOpenDialog, (void **)&dialog);
    if (FAILED(picker->result)) goto done;
    picker->result = IFileOpenDialog_GetOptions(dialog, &options);
    if (FAILED(picker->result)) goto done;
    picker->result = IFileOpenDialog_SetOptions(dialog, options | FOS_PICKFOLDERS |
                                               FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_DONTADDTORECENT);
    if (FAILED(picker->result)) goto done;
    IFileOpenDialog_SetTitle(dialog, L"Select Yadof installation folder");
    IFileOpenDialog_SetOkButtonLabel(dialog, L"Select folder");

    /* A new default prefix may not exist yet. Start at its nearest existing parent. */
    for (;;) {
        DWORD attributes = GetFileAttributesW(picker->initial);
        if (attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY)) break;
        size_t length = wcslen(picker->initial);
        while (length > 3 && (picker->initial[length - 1] == L'\\' || picker->initial[length - 1] == L'/'))
            picker->initial[--length] = L'\0';
        WCHAR *slash = wcsrchr(picker->initial, L'\\');
        if (!slash || slash <= picker->initial + 2) break;
        slash[0] = L'\0';
    }
    if (SUCCEEDED(SHCreateItemFromParsingName(picker->initial, NULL, &IID_IShellItem, (void **)&folder)))
        IFileOpenDialog_SetFolder(dialog, folder);

    /* The remote CA host must not synchronously message a blocked client owner. */
    picker->result = IFileOpenDialog_Show(dialog, NULL);
    if (FAILED(picker->result)) goto done;
    picker->result = IFileOpenDialog_GetResult(dialog, &selected);
    if (SUCCEEDED(picker->result))
        picker->result = IShellItem_GetDisplayName(selected, SIGDN_FILESYSPATH, &picker->selected);

done:
    if (selected) IShellItem_Release(selected);
    if (folder) IShellItem_Release(folder);
    if (dialog) IFileOpenDialog_Release(dialog);
    CoUninitialize();
}

__declspec(dllexport) UINT __stdcall PickInstallFolder(MSIHANDLE session)
{
    Picker picker = {0};
    DWORD length = ARRAYSIZE(picker.initial);
    UINT status = MsiGetPropertyW(session, L"INSTALLDIR", picker.initial, &length);
    if (status != ERROR_SUCCESS) return status;

    /* Stay on MSI's impersonated UI-action thread; a new thread would lose the
       user's impersonation token in the remote custom-action host. */
    choose_folder(&picker);

    if (picker.result == HRESULT_FROM_WIN32(ERROR_CANCELLED)) return ERROR_SUCCESS;
    if (FAILED(picker.result) || !picker.selected) {
        MSIHANDLE message = MsiCreateRecord(0);
        MsiRecordSetStringW(message, 0, L"Yadof could not open the Windows folder selector.");
        MsiProcessMessage(session, INSTALLMESSAGE_ERROR, message);
        MsiCloseHandle(message);
        return ERROR_INSTALL_FAILURE;
    }
    if (path_fits(session, picker.selected))
        status = MsiSetTargetPathW(session, L"INSTALLDIR", picker.selected);
    else {
        MessageBoxW(NULL, path_error, L"Choose a shorter installation folder", MB_OK | MB_ICONWARNING);
        status = ERROR_SUCCESS;
    }
    CoTaskMemFree(picker.selected);
    return status;
}
