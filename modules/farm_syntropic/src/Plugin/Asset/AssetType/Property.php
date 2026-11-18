<?php

declare(strict_types=1);

namespace Drupal\farm_syntropic\Plugin\Asset\AssetType;

use Drupal\Core\StringTranslation\TranslatableMarkup;
use Drupal\farm_entity\Attribute\AssetType;
use Drupal\farm_entity\Plugin\Asset\AssetType\FarmAssetType;

/**
 * Provides the property (client parcel) asset type.
 *
 * A property is the client's parcel the consult dashboard designs for. It
 * lives in the one shared farmOS instance alongside the home farm; consult
 * areas (grove-odoo-modules, section C) reference it, and its trees carry
 * tenure `client`. No behaviour beyond field definitions — the consult
 * workflow lives in Odoo and grove-sites.
 */
#[AssetType(
  id: 'property',
  label: new TranslatableMarkup('Property'),
)]
class Property extends FarmAssetType {

  /**
   * {@inheritdoc}
   */
  public function buildFieldDefinitions() {
    $fields = parent::buildFieldDefinitions();

    $field_info = [
      'client_name' => [
        'type' => 'string',
        'label' => $this->t('Client name'),
        'description' => $this->t('The landowner this property belongs to.'),
        'weight' => ['form' => -90, 'view' => -90],
      ],
      'odoo_opportunity_id' => [
        'type' => 'integer',
        'label' => $this->t('Odoo opportunity id'),
        'description' => $this->t('The crm.lead (opportunity) id in Odoo that tracks this consult.'),
        'weight' => ['form' => -85, 'view' => -85],
      ],
      'odoo_stock_location_id' => [
        'type' => 'integer',
        'label' => $this->t('Odoo stock location id'),
        'description' => $this->t('The per-client Odoo stock location id used for lot traceability during the install.'),
        'weight' => ['form' => -80, 'view' => -80],
      ],
      // Explicit record status for the consult dashboard. Distinct from the
      // asset's built-in archived flag so the dashboard can read it directly;
      // at handover the record is archived and this flips to 'archived'.
      'status' => [
        'type' => 'list_string',
        'label' => $this->t('Status'),
        'description' => $this->t('Whether this property is an active engagement or archived at handover.'),
        'allowed_values' => [
          'active' => 'Active',
          'archived' => 'Archived',
        ],
        'weight' => ['form' => -75, 'view' => -75],
      ],
      // The parcel outline. Open-ended WKT (Polygon in practice).
      'geometry' => [
        'type' => 'geofield',
        'label' => $this->t('Geometry'),
        'description' => $this->t("The client parcel's boundary polygon."),
        'weight' => ['form' => 0, 'view' => 0],
      ],
    ];

    foreach ($field_info as $name => $info) {
      $fields[$name] = $this->farmFieldFactory->bundleFieldDefinition($info);
    }

    return $fields;
  }

}
