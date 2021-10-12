/*
 * Copyright (c) 2017-2021 Arm Limited
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "stdio.h"
#include "string.h"
#include "cmsis.h"
#include "serial.h"
#include "print_log.h"

#include "blink_task.h"
#include "ml_interface.h"

#include "FreeRTOS.h"
#include "task.h"
#include "FreeRTOS_IP.h"

/* includes for TFM */
#include "tfm_ns_interface.h"
#include "psa/protected_storage.h"
#include "psa/crypto.h"

/* includes for IoT Cloud */
#include "iot_mqtt.h"
#include "iot_secure_sockets.h"
#include "iot_network_freertos.h"
#include "iot_logging_task.h"
#include "aws_dev_mode_key_provisioning.h"
#include "psa/update.h"

extern int mbedtls_platform_set_calloc_free( void * (*calloc_func)( size_t, size_t ),
                                             void (*free_func)( void * ) );
static void * prvCalloc( size_t xNmemb,
                         size_t xSize );

extern void DEMO_RUNNER_RunDemos( void );

/*
 * Semihosting is a mechanism that enables code running on an ARM target
 * to communicate and use the Input/Output facilities of a host computer
 * that is running a debugger.
 * There is an issue where if you use armclang at -O0 optimisation with
 * no parameters specified in the main function, the initialisation code
 * contains a breakpoint for semihosting by default. This will stop the
 * code from running before main is reached.
 * Semihosting can be disabled by defining __ARM_use_no_argv symbol
 * (or using higher optimization level).
 */
#if defined (__ARMCC_VERSION) && (__ARMCC_VERSION >= 6010050)
__asm("  .global __ARM_use_no_argv\n");
#endif

extern uint32_t tfm_ns_interface_init(void);

#define FREERTOS_HIGHEST_TASK_PRIORITY      (configMAX_PRIORITIES - 1)

uint8_t ucHeap[ configTOTAL_HEAP_SIZE ];

/**
 * Network information
*/
/* The MAC address array is not declared const as the MAC address will
normally be read from an EEPROM and not hard coded (in real deployed
applications).*/
static uint8_t ucMACAddress[ 6 ] = { 0x00, 0x02, 0xF7, 0x00, 0x74, 0x15 };  // mac of my MPS3 eth
/* Define the network addressing.  These parameters will be used if either
ipconfigUDE_DHCP is 0 or if ipconfigUSE_DHCP is 1 but DHCP auto configuration
failed. */
static uint8_t ucIPAddress[ 4 ] = { 192, 168, 1, 215 };
static uint8_t ucNetMask[ 4 ] = { 255, 0, 0, 0 };
static uint8_t ucGatewayAddress[ 4 ] = { 10, 10, 10, 1 };
/* The following is the address of an OpenDNS server. */
static uint8_t ucDNSServerAddress[ 4 ] = { 208, 67, 222, 222 };

psa_key_handle_t xOTACodeVerifyKeyHandle = NULL;

void print_version()
{
    psa_image_info_t xImageInfo = { 0 };
    psa_image_id_t ulImageID = FWU_CALCULATE_IMAGE_ID(FWU_IMAGE_ID_SLOT_ACTIVE, FWU_IMAGE_ID_SLOT_ACTIVE, 0);
    psa_status_t uxStatus = psa_fwu_query( ulImageID, &xImageInfo );
    if( uxStatus != PSA_SUCCESS )
    {
        print_log("Firmware version: %d.%d.%d",
                  xImageInfo.version.iv_major,
                  xImageInfo.version.iv_minor,
                  xImageInfo.version.iv_revision);
    }
}

int main()
{
    BaseType_t ret = pdPASS;

    tfm_ns_interface_init();

    vUARTLockInit();

    serial_init();

    xTaskCreate(ml_task,    "ML task",    configMINIMAL_STACK_SIZE*4, NULL, tskIDLE_PRIORITY+1, NULL);
    xTaskCreate(blink_task, "blink task", configMINIMAL_STACK_SIZE*2, NULL, tskIDLE_PRIORITY,   NULL);

    xLoggingTaskInitialize(configMINIMAL_STACK_SIZE, tskIDLE_PRIORITY+2, 90);

    // FIXME: put static bool variable guard here so this only runs once ?
    mbedtls_platform_set_calloc_free( prvCalloc, vPortFree );
    vDevModeKeyProvisioning();

    ret = ota_privision_code_signing_key(&xOTACodeVerifyKeyHandle);
    configASSERT( ret == 0 );

    print_version();

    /* Initialise the RTOS's TCP/IP stack.  The tasks that use the network
    are created in the vApplicationIPNetworkEventHook() hook function
    below.  The hook function is called when the network connects. */
    print_log("IP init\r\n");
    ret = FreeRTOS_IPInit( ucIPAddress,
                           ucNetMask,
                           ucGatewayAddress,
                           ucDNSServerAddress,
                           ucMACAddress );

    print_log("starting scheduler from ns main\r\n");
    /* Start the scheduler itself. */
    vTaskStartScheduler();

    print_log("End of main. Halting!\r\n");
    while (1)
    {
    }
}


void vApplicationIPNetworkEventHook( eIPCallbackEvent_t eNetworkEvent )
{
    if (eNetworkEvent == eNetworkUp) {
        print_log("[INF] network up, starting demo\r\n");

        if (strcmp(clientcredentialMQTT_BROKER_ENDPOINT, "endpointid.amazonaws.com") == 0) {
            print_log("[ERR] INVALID CREDENTIALS AND ENDPOINT.\r\n");
            print_log("[ERR] Set the right configuration and credentials in aws_clientcredential.h and aws_clientcredential_keys.h\r\n");
            // Start the inference directly
            ml_task_inference_start();
        } else {
            DEMO_RUNNER_RunDemos( );
        }
    } else {
        print_log("[ERR] network down\r\n");
    }


}


/**
 * @brief Implements libc calloc semantics using the FreeRTOS heap
 */
static void * prvCalloc( size_t xNmemb, size_t xSize )
{
    void * pvNew = pvPortMalloc( xNmemb * xSize );

    if( NULL != pvNew )
    {
        memset( pvNew, 0, xNmemb * xSize );
    }

    return pvNew;
}
