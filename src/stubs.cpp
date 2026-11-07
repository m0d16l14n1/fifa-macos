// Kernel exports FIFA's engine imports that the SDK does not implement (the same pair ReStreet stubs).
#include <rex/hook.h>

REX_EXPORT_STUB_RETURN(__imp__XUsbcamGetState, 0);
REX_EXPORT_STUB_RETURN(__imp__XUsbcamSetConfig, 0);
