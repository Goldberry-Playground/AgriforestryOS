<?php

declare(strict_types=1);

namespace Drupal\farm_syntropic\Plugin\Asset\AssetType;

use Drupal\Core\StringTranslation\TranslatableMarkup;
use Drupal\farm_entity\Attribute\AssetType;
use Drupal\farm_entity\Plugin\Asset\AssetType\FarmAssetType;

/**
 * Provides the water asset type (pond, stream, wet spot).
 *
 * Geometry is open-ended WKT so it can hold a Point (a spring or wet spot)
 * or a Polygon (a pond outline), per the consult design. No behaviour beyond
 * field definitions.
 */
#[AssetType(
  id: 'water',
  label: new TranslatableMarkup('Water'),
)]
class Water extends FarmAssetType {

  /**
   * {@inheritdoc}
   */
  public function buildFieldDefinitions() {
    $fields = parent::buildFieldDefinitions();

    $field_info = [
      'notes' => [
        'type' => 'text_long',
        'label' => $this->t('Notes'),
        'description' => $this->t('Free-form notes about this water feature.'),
        'weight' => ['form' => -10, 'view' => -10],
      ],
      // Point (wet spot / spring) or Polygon (pond). No geometry-type
      // validator, matching the tree_planting convention.
      'geometry' => [
        'type' => 'geofield',
        'label' => $this->t('Geometry'),
        'description' => $this->t('Point or Polygon geometry for the water feature.'),
        'weight' => ['form' => 0, 'view' => 0],
      ],
    ];

    foreach ($field_info as $name => $info) {
      $fields[$name] = $this->farmFieldFactory->bundleFieldDefinition($info);
    }

    return $fields;
  }

}
